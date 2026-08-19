use memchr::{memchr_iter, memmem};
use memmap2::Mmap;
use pyo3::prelude::*;
use rayon::prelude::*;
use regex::bytes::RegexBuilder;
use std::fs::File;
use std::path::Path;
use std::sync::atomic::{AtomicI32, AtomicUsize, Ordering};
use std::sync::Arc;

#[pyclass]
struct FileIndexCore {
    file_path: String,
    line_offsets: Vec<u64>,
    file_size: usize,
    mmap: Option<Arc<Mmap>>,
}

#[pymethods]
impl FileIndexCore {
    #[new]
    fn new() -> Self {
        FileIndexCore {
            file_path: String::new(),
            line_offsets: Vec::new(),
            file_size: 0,
            mmap: None,
        }
    }

    #[pyo3(signature = (file_path, progress_callback = None))]
    fn index_file(
        &mut self,
        py: Python<'_>,
        file_path: String,
        progress_callback: Option<PyObject>,
    ) -> PyResult<usize> {
        let path = Path::new(&file_path);
        let file = File::open(path)?;
        let mmap = unsafe { Arc::new(Mmap::map(&file)?) };

        self.file_path = file_path;
        self.file_size = mmap.len();
        self.mmap = Some(mmap.clone());

        if self.file_size == 0 {
            self.line_offsets = vec![0];
            return Ok(1);
        }

        let file_size = self.file_size;
        let chunk_size = 32 * 1024 * 1024; // 32MB

        let (line_offsets, _) = py.allow_threads(|| {
            let num_chunks = (file_size + chunk_size - 1) / chunk_size;
            let total_processed = Arc::new(AtomicUsize::new(0));
            let last_reported_pct = Arc::new(AtomicI32::new(-1));

            let mut chunks_offsets: Vec<Vec<u64>> = (0..num_chunks)
                .into_par_iter()
                .map(|i| {
                    let start = i * chunk_size;
                    let end = std::cmp::min(start + chunk_size, file_size);
                    let sub_slice = &mmap[start..end];

                    let mut local_offsets = Vec::with_capacity(sub_slice.len() / 80 + 1024);
                    for pos in memchr_iter(b'\n', sub_slice) {
                        local_offsets.push((start + pos + 1) as u64);
                    }

                    if let Some(ref callback) = progress_callback {
                        let processed = total_processed.fetch_add(end - start, Ordering::Relaxed) + (end - start);
                        let pct = ((processed as f64 / file_size as f64) * 100.0) as i32;

                        let mut current_pct = last_reported_pct.load(Ordering::Relaxed);
                        while pct > current_pct {
                            match last_reported_pct.compare_exchange_weak(
                                current_pct,
                                pct,
                                Ordering::Relaxed,
                                Ordering::Relaxed,
                            ) {
                                Ok(_) => {
                                    Python::with_gil(|py_callback| {
                                        let _ = callback.call1(py_callback, (pct, 0));
                                    });
                                    break;
                                }
                                Err(actual) => current_pct = actual,
                            }
                        }
                    }

                    local_offsets
                })
                .collect();

            let total_lines: usize = chunks_offsets.iter().map(|c| c.len()).sum::<usize>() + 1;
            let mut final_offsets = Vec::with_capacity(total_lines);
            final_offsets.push(0u64);

            for mut offsets in chunks_offsets.drain(..) {
                final_offsets.append(&mut offsets);
            }

            if let Some(&last) = final_offsets.last() {
                if last >= file_size as u64 {
                    final_offsets.pop();
                }
            }

            (final_offsets, total_lines)
        });

        self.line_offsets = line_offsets;
        Ok(self.line_offsets.len())
    }

    fn get_offsets_range(&self, start_idx: usize, count: usize) -> Vec<u64> {
        let len = self.line_offsets.len();
        if start_idx >= len {
            return vec![];
        }
        let end_idx = std::cmp::min(start_idx + count, len);
        self.line_offsets[start_idx..end_idx].to_vec()
    }

    #[pyo3(signature = (pattern, use_regex = false))]
    fn search_keyword(
        &self,
        py: Python<'_>,
        pattern: Vec<u8>,
        use_regex: bool,
    ) -> PyResult<(Vec<String>, Vec<usize>, usize)> {
        if pattern.is_empty() || self.mmap.is_none() || self.line_offsets.is_empty() {
            return Ok((vec![], vec![], 0));
        }

        let mmap = self.mmap.as_ref().unwrap().clone();
        let line_offsets = &self.line_offsets;

        // 청크별 매칭된 라인 번호들을 수집 (개수 제한 없이 수집)
        let results: Result<Vec<Vec<usize>>, pyo3::PyErr> = py.allow_threads(|| {
            let chunk_size = 16 * 1024 * 1024; // 16MB
            let file_len = mmap.len();

            let chunks: Vec<(usize, usize)> = (0..file_len)
                .step_by(chunk_size)
                .map(|start| {
                    let end = std::cmp::min(start + chunk_size, file_len);
                    (start, end)
                })
                .collect();

            if use_regex {
                let pattern_str = std::str::from_utf8(&pattern).map_err(|_| {
                    pyo3::exceptions::PyValueError::new_err("Invalid UTF-8 regex pattern")
                })?;

                let re = RegexBuilder::new(pattern_str)
                    .multi_line(true)
                    .build()
                    .map_err(|e| {
                        pyo3::exceptions::PyValueError::new_err(format!("Regex syntax error: {}", e))
                    })?;

                let overlap: usize = 1024;

                Ok(chunks
                    .into_par_iter()
                    .map(|(c_start, c_end)| {
                        let search_end = std::cmp::min(c_end + overlap, file_len);
                        let sub_slice = &mmap[c_start..search_end];
                        let mut local_indices = Vec::new();
                        let mut last_line_idx = None;
                        let primary_len = c_end - c_start;

                        for m in re.find_iter(sub_slice) {
                            // 오버랩 영역에서 시작된 매치는 다음 청크에서 처리하도록 제어
                            if m.start() >= primary_len {
                                break;
                            }
                            let abs_offset = (c_start + m.start()) as u64;
                            let line_idx = match line_offsets.binary_search(&abs_offset) {
                                Ok(idx) => idx,
                                Err(idx) => idx.saturating_sub(1),
                            };

                            if Some(line_idx) != last_line_idx {
                                local_indices.push(line_idx);
                                last_line_idx = Some(line_idx);
                            }
                        }
                        local_indices
                    })
                    .collect())
            } else {
                let finder = memmem::Finder::new(&pattern);

                Ok(chunks
                    .into_par_iter()
                    .map(|(c_start, c_end)| {
                        let search_end = std::cmp::min(c_end + pattern.len() - 1, file_len);
                        let sub_slice = &mmap[c_start..search_end];
                        let mut local_indices = Vec::new();
                        let mut last_line_idx = None;

                        for pos in finder.find_iter(sub_slice) {
                            let abs_offset = (c_start + pos) as u64;
                            let line_idx = match line_offsets.binary_search(&abs_offset) {
                                Ok(idx) => idx,
                                Err(idx) => idx.saturating_sub(1),
                            };

                            if Some(line_idx) != last_line_idx {
                                local_indices.push(line_idx);
                                last_line_idx = Some(line_idx);
                            }
                        }
                        local_indices
                    })
                    .collect())
            }
        });

        // 1. 모든 청크의 결과를 하나로 통합
        let mut final_indices = Vec::new();
        for mut chunk_res in results? {
            final_indices.append(&mut chunk_res);
        }

        // 2. 청크 경계 중복 라인 제거 및 정렬
        final_indices.sort_unstable();
        final_indices.dedup();

        // 3. 중복이 완전히 제거된 정확한 검색 라인 수 산출 (45건 오차 해결)
        let total_found = final_indices.len();

        // 4. 반환할 표시용 결과 목록을 2000개로 상한 제한 (Truncate)
        if final_indices.len() > 2000 {
            final_indices.truncate(2000);
        }

        // 5. Python 출력용 라인 문자열 생성
        let res_matches: Vec<String> = final_indices
            .iter()
            .map(|&idx| format!("Line {}", idx + 1))
            .collect();

        Ok((res_matches, final_indices, total_found))
    }

    fn get_offset(&self, index: usize) -> Option<u64> {
        self.line_offsets.get(index).copied()
    }
}

#[pymodule]
fn large_file_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<FileIndexCore>()?;
    Ok(())
}
