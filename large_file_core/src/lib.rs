use pyo3::prelude::*;
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
        let mut offsets = vec![0u64];

        if self.file_size == 0 {
            self.line_offsets = offsets;
            return Ok(0);
        }

        let chunk_size = 64 * 1024 * 1024;
        let mut last_reported_pct = -1;
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

    /// [성능 개선] 범위 단위 오프셋 일괄 반환 (파이썬 CFFI 호출 횟수 극적 감소)
    fn get_offsets_range(&self, start_idx: usize, count: usize) -> Vec<u64> {
        let end_idx = std::cmp::min(start_idx + count, self.line_offsets.len());
        if start_idx >= self.line_offsets.len() {
            return vec![];
        }
        self.line_offsets[start_idx..end_idx].to_vec()
    }

    /// [정합성 보완] 대소문자 무시/인코딩 무관 초고속 검색 수행
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

        py.allow_threads(|| {
            // 바이트 기반 정규식 패턴 생성
            let re_result = if is_regex {
                let pattern_str = String::from_utf8_lossy(&pattern);
                let mut builder = regex::bytes::RegexBuilder::new(&pattern_str);
                builder.case_insensitive(case_insensitive);
                builder.build()
            } else {
                let escaped_pattern = regex::escape(&String::from_utf8_lossy(&pattern));
                let mut builder = regex::bytes::RegexBuilder::new(&escaped_pattern);
                builder.case_insensitive(case_insensitive);
                builder.build()
            };

            if let Ok(re) = re_result {
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
                            // Python UI 호환성을 위해 Line 라벨 형태로 통일
                            matches.push(format!("Line {}", line_idx + 1));
                        }
                        last_line_idx = Some(line_idx);
                    }
                    if total_found >= 2000 { break; }
                }
            }
        });

        Ok((matches, line_indices, total_found))
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
