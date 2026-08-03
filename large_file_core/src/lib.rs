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

        let results: Vec<Vec<usize>> = py.allow_threads(|| {
            let chunk_size = 32 * 1024 * 1024;
            let file_len = mmap.len();

            let chunks: Vec<(usize, usize)> = (0..file_len)
                .step_by(chunk_size)
                .map(|start| {
                    let end = std::cmp::min(start + chunk_size, file_len);
                    (start, end)
                })
                .collect();

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

                let local_results: Result<Vec<Vec<usize>>, pyo3::PyErr> = chunks
                    .into_par_iter()
                    .map(|(c_start, c_end)| {
                        let sub_slice = &mmap[c_start..c_end];
                        let mut local_indices = Vec::new();
                        let mut last_line_idx = None;

                        let start_line_idx = match line_offsets.binary_search(&(c_start as u64)) {
                            Ok(idx) => idx,
                            Err(idx) => idx.saturating_sub(1),
                        };
                        let end_line_idx = match line_offsets.binary_search(&(c_end as u64)) {
                            Ok(idx) => idx,
                            Err(idx) => idx,
                        };
                        let local_slice = &line_offsets[start_line_idx..std::cmp::min(end_line_idx + 1, line_offsets.len())];

                        for m in re.find_iter(sub_slice) {
                            let abs_offset = c_start + m.start();
                            let local_idx = match local_slice.binary_search(&(abs_offset as u64)) {
                                Ok(idx) => idx,
                                Err(idx) => idx.saturating_sub(1),
                            };
                            let line_idx = start_line_idx + local_idx;

                            if Some(line_idx) != last_line_idx {
                                local_indices.push(line_idx);
                                last_line_idx = Some(line_idx);
                                if local_indices.len() >= 2000 {
                                    break;
                                }
                            }
                        }
                        Ok(local_indices)
                    })
                    .collect();

                local_results
            } else {
                let local_results: Result<Vec<Vec<usize>>, pyo3::PyErr> = chunks
                    .into_par_iter()
                    .map(|(c_start, c_end)| {
                        let search_end = std::cmp::min(c_end + pattern.len(), file_len);
                        let sub_slice = &mmap[c_start..search_end];
                        let mut local_indices = Vec::new();
                        let mut last_line_idx = None;

                        if !sub_slice.contains(&pattern[0]) {
                            return Ok(local_indices);
                        }

                        let start_line_idx = match line_offsets.binary_search(&(c_start as u64)) {
                            Ok(idx) => idx,
                            Err(idx) => idx.saturating_sub(1),
                        };
                        let end_line_idx = match line_offsets.binary_search(&(search_end as u64)) {
                            Ok(idx) => idx,
                            Err(idx) => idx,
                        };
                        let local_slice = &line_offsets[start_line_idx..std::cmp::min(end_line_idx + 1, line_offsets.len())];

                        let finder = memmem::Finder::new(&pattern);
                        for pos in finder.find_iter(sub_slice) {
                            let abs_offset = c_start + pos;
                            let local_idx = match local_slice.binary_search(&(abs_offset as u64)) {
                                Ok(idx) => idx,
                                Err(idx) => idx.saturating_sub(1),
                            };
                            let line_idx = start_line_idx + local_idx;

                            if Some(line_idx) != last_line_idx {
                                local_indices.push(line_idx);
                                last_line_idx = Some(line_idx);
                                if local_indices.len() >= 2000 {
                                    break;
                                }
                            }
                        }
                        Ok(local_indices)
                    })
                    .collect();

                local_results
            }
        })?;

        let mut final_indices = Vec::new();
        for mut chunk_res in results {
            final_indices.append(&mut chunk_res);
        }
        final_indices.sort_unstable();
        final_indices.dedup();

        let total_found = final_indices.len();
        if final_indices.len() > 2000 {
            final_indices.truncate(2000);
        }

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
