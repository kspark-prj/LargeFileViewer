use memchr::{memchr_iter, memmem};
use memmap2::Mmap;
use pyo3::prelude::*;
use rayon::prelude::*;
use regex::bytes::RegexBuilder;
use std::fs::File;
use std::path::Path;
use std::sync::{Arc, Mutex};

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
            return Ok(0);
        }

        let chunk_size = 64 * 1024 * 1024;
        let file_size = self.file_size;

        let estimated_lines = (file_size / 80).max(1024);
        let offsets_arc = Arc::new(Mutex::new(Vec::with_capacity(estimated_lines)));
        {
            let mut guard = offsets_arc.lock().unwrap();
            guard.push(0u64);
        }

        let last_reported_pct = Arc::new(Mutex::new(-1i32));

        py.allow_threads(|| {
            let mut current_pos = 0;
            while current_pos < file_size {
                let end_pos = std::cmp::min(current_pos + chunk_size, file_size);
                let sub_slice = &mmap[current_pos..end_pos];

                let mut local_offsets = Vec::with_capacity(65536);
                for pos in memchr_iter(b'\n', sub_slice) {
                    local_offsets.push((current_pos + pos + 1) as u64);
                }

                let current_len = {
                    let mut guard = offsets_arc.lock().unwrap();
                    guard.extend_from_slice(&local_offsets);
                    guard.len()
                };

                if let Some(ref callback) = progress_callback {
                    let pct = ((end_pos as f64 / file_size as f64) * 100.0) as i32;
                    let mut last_pct = last_reported_pct.lock().unwrap();
                    if pct > *last_pct {
                        *last_pct = pct;
                        Python::with_gil(|py_callback| {
                            let _ = callback.call1(py_callback, (pct, current_len));
                        });
                    }
                }
                current_pos = end_pos;
            }
        });

        let mut final_offsets = match Arc::try_unwrap(offsets_arc) {
            Ok(mutex) => mutex.into_inner().unwrap(),
            Err(arc) => arc.lock().unwrap().clone(),
        };

        if let Some(&last) = final_offsets.last() {
            if last > file_size as u64 {
                final_offsets.pop();
            }
        }

        self.line_offsets = final_offsets;
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
        if pattern.is_empty() || self.mmap.is_none() {
            return Ok((vec![], vec![], 0));
        }

        let mmap = self.mmap.as_ref().unwrap().clone();
        let line_offsets = &self.line_offsets;

        let line_indices = Arc::new(Mutex::new(Vec::with_capacity(2000)));
        let total_found = Arc::new(Mutex::new(0usize));

        if use_regex {
            let pattern_str = match std::str::from_utf8(&pattern) {
                Ok(s) => s,
                Err(_) => {
                    return Err(pyo3::exceptions::PyValueError::new_err(
                        "Invalid UTF-8 regex pattern",
                    ))
                }
            };

            let re = match RegexBuilder::new(pattern_str).multi_line(true).build() {
                Ok(r) => r,
                Err(e) => {
                    return Err(pyo3::exceptions::PyValueError::new_err(format!(
                        "Regex syntax error: {}",
                        e
                    )))
                }
            };

            py.allow_threads(|| {
                let mut last_line_idx = None;

                for m in re.find_iter(&mmap) {
                    let offset = m.start() as u64;

                    let line_idx = match line_offsets.binary_search(&offset) {
                        Ok(idx) => idx,
                        Err(idx) => {
                            if idx > 0 {
                                idx - 1
                            } else {
                                0
                            }
                        }
                    };

                    if Some(line_idx) != last_line_idx {
                        let mut tf = total_found.lock().unwrap();
                        *tf += 1;

                        let mut li = line_indices.lock().unwrap();
                        if li.len() < 2000 {
                            li.push(line_idx);
                        } else {
                            break;
                        }
                        last_line_idx = Some(line_idx);
                    }
                }
            });
        } else {
            py.allow_threads(|| {
                let chunk_size = 32 * 1024 * 1024;
                let file_len = mmap.len();

                let chunks: Vec<(usize, usize)> = (0..file_len)
                    .step_by(chunk_size)
                    .map(|start| {
                        (
                            start,
                            std::cmp::min(start + chunk_size + pattern.len(), file_len),
                        )
                    })
                    .collect();

                chunks.into_par_iter().for_each(|(c_start, c_end)| {
                    let sub_slice = &mmap[c_start..c_end];

                    if !sub_slice.contains(&pattern[0]) {
                        return;
                    }

                    let finder = memmem::Finder::new(&pattern);
                    for pos in finder.find_iter(sub_slice) {
                        let abs_offset = (c_start + pos) as u64;

                        let line_idx = match line_offsets.binary_search(&abs_offset) {
                            Ok(idx) => idx,
                            Err(idx) => {
                                if idx > 0 {
                                    idx - 1
                                } else {
                                    0
                                }
                            }
                        };

                        let mut tf = total_found.lock().unwrap();
                        if *tf >= 2000 {
                            break;
                        }

                        let mut li = line_indices.lock().unwrap();
                        if li.is_empty() || *li.last().unwrap() != line_idx {
                            *tf += 1;
                            if li.len() < 2000 {
                                li.push(line_idx);
                            }
                        }
                    }
                });
            });
        }

        let mut res_indices = match Arc::try_unwrap(line_indices) {
            Ok(mutex) => mutex.into_inner().unwrap(),
            Err(arc) => arc.lock().unwrap().clone(),
        };

        res_indices.sort_unstable();
        res_indices.dedup();

        let res_matches: Vec<String> = res_indices
            .iter()
            .map(|&idx| format!("Line {}", idx + 1))
            .collect();

        let res_total = *total_found.lock().unwrap();

        Ok((res_matches, res_indices, res_total))
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
