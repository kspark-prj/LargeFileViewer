use pyo3::prelude::*;
use pyo3::types::PyBytes;
use memmap2::Mmap;
use std::fs::File;
use std::path::Path;
use memchr::memchr_iter;

#[pyclass]
struct FileIndexCore {
    file_path: String,
    line_offsets: Vec<u64>,
    file_size: usize,
}

#[pymethods]
impl FileIndexCore {
    #[new]
    fn new() -> Self {
        FileIndexCore {
            file_path: String::new(),
            line_offsets: vec![0u64],
            file_size: 0,
        }
    }

    /// 대용량 파일을 인덱싱하고 내부 line_offsets 벡터에 저장합니다.
    #[pyo3(signature = (file_path, progress_callback = None))]
    fn index_file(&mut self, py: Python<'_>, file_path: String, progress_callback: Option<PyObject>) -> PyResult<usize> {
        let path = Path::new(&file_path);
        let file = File::open(path)?;
        let mmap = unsafe { Mmap::map(&file)? };

        self.file_path = file_path;
        self.file_size = mmap.len();
        self.line_offsets = vec![0u64];

        if self.file_size == 0 {
            return Ok(0);
        }

        let chunk_size = 64 * 1024 * 1024;
        let mut last_reported_pct = -1;

        // 거대한 루프 전체를 GIL 해제 상태로 안전하게 실행
        let mut offsets = std::mem::take(&mut self.line_offsets);
        let file_size = self.file_size;

        py.allow_threads(|| {
            let mut current_pos = 0;
            while current_pos < file_size {
                let end_pos = std::cmp::min(current_pos + chunk_size, file_size);
                let sub_slice = &mmap[current_pos..end_pos];

                for pos in memchr_iter(b'\n', sub_slice) {
                    offsets.push((current_pos + pos + 1) as u64);
                }

                if let Some(ref callback) = progress_callback {
                    let pct = ((end_pos as f64 / file_size as f64) * 100.0) as i32;
                    if pct > last_reported_pct {
                        last_reported_pct = pct;
                        let line_count = offsets.len();

                        // 파이썬 UI 업데이트를 위한 콜백 시에만 잠깐 GIL 획득
                        Python::with_gil(|py_callback| {
                            let _ = callback.call1(py_callback, (pct, line_count));
                        });
                    }
                }
                current_pos = end_pos;
            }
        });

        self.line_offsets = offsets;
        Ok(self.line_offsets.len())
    }

    /// Rust 내부 메모리의 line_offsets를 참조하여 초고속 검색을 수행합니다. (파이썬 데이터 복사 0)
    fn search_keyword(
        &self,
        py: Python<'_>,
        pattern: Vec<u8>,
        is_regex: bool,
        case_insensitive: bool,
    ) -> PyResult<(Vec<String>, Vec<usize>, usize)> {
        let path = Path::new(&self.file_path);
        let file = File::open(path)?;
        let mmap = unsafe { Mmap::map(&file)? };

        let mut matches = Vec::new();
        let mut line_indices = Vec::new();
        let mut total_found = 0;

        let line_offsets = &self.line_offsets;

        // 헬퍼 클로저
        let get_line_string = |idx: usize, offsets: &[u64], map_data: &[u8]| -> String {
            let start = offsets[idx] as usize;
            let end = if idx + 1 < offsets.len() { offsets[idx + 1] as usize } else { map_data.len() };
            let line_bytes = &map_data[start..end];
            let trimmed_bytes = if line_bytes.ends_with(b"\r\n") {
                &line_bytes[..line_bytes.len() - 2]
            } else if line_bytes.ends_with(b"\n") {
                &line_bytes[..line_bytes.len() - 1]
            } else {
                line_bytes
            };
            String::from_utf8_lossy(trimmed_bytes).into_owned()
        };

        // GIL 해제 후 검색 연산 수행
        py.allow_threads(|| {
            if is_regex {
                if let Ok(pattern_str) = std::str::from_utf8(&pattern) {
                    let mut builder = regex::bytes::RegexBuilder::new(pattern_str);
                    if case_insensitive { builder.case_insensitive(true); }

                    if let Ok(re) = builder.build() {
                        let mut current_search_start = 0;
                        let mut last_line_idx = None;

                        for mat in re.find_iter(&mmap) {
                            let offset = mat.start() as u64;
                            let search_slice = &line_offsets[current_search_start..];

                            let line_idx = match search_slice.binary_search(&offset) {
                                Ok(idx) => current_search_start + idx,
                                Err(idx) => if idx > 0 { current_search_start + idx - 1 } else { current_search_start },
                            };

                            current_search_start = line_idx;

                            if Some(line_idx) != last_line_idx {
                                total_found += 1;
                                if line_indices.len() < 2000 {
                                    line_indices.push(line_idx);
                                    matches.push(get_line_string(line_idx, line_offsets, &mmap));
                                }
                                last_line_idx = Some(line_idx);
                            }
                            if total_found >= 2000 { break; }
                        }
                    }
                }
            } else {
                let finder = memchr::memmem::Finder::new(&pattern);
                let mut current_search_start = 0;
                let mut last_line_idx = None;

                for offset in finder.find_iter(&mmap) {
                    let offset_u64 = offset as u64;
                    let search_slice = &line_offsets[current_search_start..];

                    let line_idx = match search_slice.binary_search(&offset_u64) {
                        Ok(idx) => current_search_start + idx,
                        Err(idx) => if idx > 0 { current_search_start + idx - 1 } else { current_search_start },
                    };

                    current_search_start = line_idx;

                    if Some(line_idx) != last_line_idx {
                        total_found += 1;
                        if line_indices.len() < 2000 {
                            line_indices.push(line_idx);
                            matches.push(get_line_string(line_idx, line_offsets, &mmap));
                        }
                        last_line_idx = Some(line_idx);
                    }
                    if total_found >= 2000 { break; }
                }
            }
        });

        Ok((matches, line_indices, total_found))
    }

    /// 파일 뷰어 연산(특정 라인 범위 읽기) 최적화를 위해 특정 라인의 오프셋만 파이썬에 반환
    fn get_offset(&self, index: usize) -> Option<u64> {
        self.line_offsets.get(index).copied()
    }
}

#[pymodule]
fn large_file_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<FileIndexCore>()?;
    Ok(())
}
