//! Default-off copying of existing scientific values. No RNG or sampling API.
use serde::Serialize;
use serde_json::json;
use six_primitives_core::substrate::MarkovKernel;
use std::fs::{self, File};
use std::io::{self, BufWriter, Write};
use std::path::Path;

fn stem(exp: &str, label: &str, seed: u64) -> String {
    // Internal named-family labels include punctuation. Percent-encode it
    // without changing the scientific label or introducing filename collisions.
    let escape = |value: &str| -> String {
        value.bytes().map(|byte| {
            if byte.is_ascii_alphanumeric() || byte == b'_' || byte == b'-' {
                (byte as char).to_string()
            } else {
                format!("%{byte:02X}")
            }
        }).collect()
    };
    format!("{}__{}__{seed}", escape(exp), escape(label))
}

#[cfg(test)]
mod tests {
    #[test]
    fn punctuation_labels_are_safe_and_distinct() {
        assert_eq!(super::stem("EXP-102", "P2=0.3", 7), "EXP-102__P2%3D0%2E3__7");
        assert_ne!(super::stem("EXP-102", "P2=0.3", 7), super::stem("EXP-102", "P2%3D0%2E3", 7));
        assert!(!super::stem("EXP-102", "A/B", 7).contains('/'));
    }
}

fn write<T: Serialize>(dir: &Path, name: &str, value: &T) -> io::Result<()> {
    fs::create_dir_all(dir)?;
    let path = dir.join(name);
    let temporary = path.with_extension("partial");
    let mut output = BufWriter::new(File::create(&temporary)?);
    serde_json::to_writer(&mut output, value).map_err(io::Error::other)?;
    output.write_all(b"\n")?;
    output.flush()?;
    output.get_ref().sync_all()?;
    fs::rename(temporary, path)
}

pub fn kernel(dir: &Path, exp: &str, label: &str, seed: u64,
              kernel: &MarkovKernel, active_tau: Option<usize>, steps: usize) -> io::Result<()> {
    write(dir, &format!("{}.kernel.json", stem(exp, label, seed)), &json!({
        "schema": "born_run_kernel_v1", "exp": exp, "config": label,
        "kernel_seed": seed, "n": kernel.n, "kernel": kernel.kernel,
        "final_active_tau": active_tau, "stochastic_program_steps": steps
    }))
}

pub fn paths(dir: &Path, exp: &str, label: &str, seed: u64, tau: usize,
             starts: &[usize], sampled_paths: &[Vec<usize>]) -> io::Result<()> {
    write(dir, &format!("{}.paths.json", stem(exp, label, seed)), &json!({
        "schema": "born_discovery_paths_v1", "exp": exp, "config": label,
        "kernel_seed": seed, "tau": tau, "starts": starts,
        "states": sampled_paths,
        "seed_rule": "kernel seed + 50000 + zero-based path index",
        "interpretation": "copied discovery samples; not Test B train/validation/locked-test samples"
    }))
}
