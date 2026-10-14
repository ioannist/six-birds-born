// Extend the historical arch_probe/join_probe with a streaming, read-only driver.
// The copied public sidecar body is unchanged; its private context_maps routine
// performs spectral partition, sector packaging and the lexicographic joint.
#[allow(dead_code)]
mod public_sidecar;
use serde_json::{json, Value};
use six_dynamics::spectral::spectral_sym_observables;
use six_primitives_core::substrate::MarkovKernel;
use std::io::{self, BufRead, Write};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let input = std::fs::File::open(std::env::args().nth(1).ok_or("input JSONL required")?)?;
    let mut out = io::BufWriter::new(io::stdout().lock());
    for line in io::BufReader::new(input).lines() {
        let c: Value = serde_json::from_str(&line?)?;
        let matrix: Vec<Vec<f64>> = serde_json::from_value(c["kernel"].clone())?;
        let n = matrix.len();
        if n == 0 || matrix.iter().any(|r| r.len() != n || r.iter().any(|v| !v.is_finite() || *v < 0.0)) {
            return Err("invalid retained matrix".into());
        }
        let kernel = MarkovKernel { n, kernel: matrix };
        let k = c["k"].as_u64().ok_or("integer resolution required")? as usize;
        if k < 2 { return Err("resolution must be at least two".into()); }
        let maps = public_sidecar::replay_context_maps(&kernel, k);
        let pi = kernel.stationary(10000, 1e-12);
        let (observable_pi, vectors) = spectral_sym_observables(&kernel, k).ok_or("missing emitted vectors")?;
        // Compare f64 bits, including signed zero, without decimal tolerances.
        let bits = |v: &[f64]| v.iter().map(|x| format!("{:016x}", x.to_bits())).collect::<Vec<_>>();
        serde_json::to_writer(&mut out, &json!({
            "index":c["index"], "unit_id":c["unit_id"], "maps":maps,
            "fallback":pi.iter().any(|v| *v <= 1e-30),
            "stationary_bits":bits(&pi), "observable_pi_bits":bits(&observable_pi),
            "emitted_vector_bits":vectors.iter().map(|v| bits(v)).collect::<Vec<_>>()
        }))?;
        writeln!(&mut out)?;
        out.flush()?;
    }
    Ok(())
}
