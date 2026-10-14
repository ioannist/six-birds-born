//! Default-off Test B export. This module only reads the final kernel and lenses.
//! Audit and record files are deliberately separate.

use rand::{Rng, SeedableRng};
use rand_chacha::ChaCha8Rng;
use serde::Serialize;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use six_dynamics::audit::ScaleScanEntry;
use six_primitives_core::substrate::MarkovKernel;
use std::collections::BTreeMap;
use std::fs::{self, File};
use std::io::{self, BufRead, BufReader, BufWriter, Write};
use std::path::{Path, PathBuf};

const BLOCK_FIRST: u64 = 910001;
const BLOCK_LAST: u64 = 910035;
const RECIPE_COUNT: usize = 24;
const REPLICATES: usize = 32;
const CALIBRATION_DRAWS: usize = 256;
const PATH_STEPS: usize = 64;

#[derive(Clone, Copy, Debug)]
pub enum Phase {
    Header,
    Complete,
    Full,
    V6TrainVal,
    V6FreshTest,
}

impl Phase {
    pub fn parse(value: &str) -> Option<Self> {
        match value {
            "header" => Some(Self::Header),
            "complete" => Some(Self::Complete),
            "full" => Some(Self::Full),
            "v6-trainval" => Some(Self::V6TrainVal),
            "v6-fresh-test" => Some(Self::V6FreshTest),
            _ => None,
        }
    }
}

struct Context {
    k: usize,
    step_index: usize,
    raw: Vec<usize>,
    package: Vec<usize>,
    joint: Vec<usize>,
    alphabet: Vec<(usize, usize)>,
}

struct PathRow {
    block: u64,
    recipe: usize,
    replicate: usize,
    states: Vec<usize>,
}

fn digest(domain: &str) -> [u8; 32] {
    Sha256::digest(domain.as_bytes()).into()
}

fn seed_at(hash: &[u8; 32], offset: usize) -> u64 {
    u64::from_le_bytes(hash[offset..offset + 8].try_into().unwrap())
}

fn calibration_domain(exp: &str, label: &str, seed: u64, recipe: usize) -> String {
    format!("TestB/v4/Y0cal/({exp}::{label},{seed},{recipe})")
}

fn path_domain(exp: &str, label: &str, block: u64, recipe: usize, replicate: usize) -> String {
    format!("TestB/v4/path/({exp}::{label},{block},{recipe},{replicate})")
}

fn json_line<W: Write, T: Serialize>(writer: &mut W, value: &T) -> io::Result<()> {
    serde_json::to_writer(&mut *writer, value).map_err(io::Error::other)?;
    writer.write_all(b"\n")
}

fn context_maps(kernel: &MarkovKernel, scan: &[ScaleScanEntry]) -> Vec<Context> {
    scan.iter()
        .enumerate()
        .filter(|(_, entry)| entry.k >= 2)
        .map(|(step_index, entry)| {
            let raw = six_dynamics::spectral::spectral_partition(kernel, entry.k);
            let package = six_dynamics::pica::p5_cells::p5_from_p4(kernel, &raw, entry.k);
            let mut alphabet: Vec<(usize, usize)> =
                raw.iter().copied().zip(package.iter().copied()).collect();
            alphabet.sort_unstable();
            alphabet.dedup();
            let by_pair: BTreeMap<(usize, usize), usize> = alphabet
                .iter()
                .copied()
                .enumerate()
                .map(|(id, pair)| (pair, id))
                .collect();
            let joint = raw
                .iter()
                .copied()
                .zip(package.iter().copied())
                .map(|pair| by_pair[&pair])
                .collect();
            Context {
                k: entry.k,
                step_index,
                raw,
                package,
                joint,
                alphabet,
            }
        })
        .collect()
}

fn safe_stem(exp: &str, label: &str, seed: u64) -> String {
    let clean = |s: &str| {
        s.chars()
            .map(|c| if c.is_ascii_alphanumeric() || c == '-' { c } else { '_' })
            .collect::<String>()
    };
    let hash = digest(&format!("{exp}::{label}"));
    let suffix = hash[..4].iter().map(|b| format!("{b:02x}")).collect::<String>();
    format!("{}__{}__{}__{}", clean(exp), clean(label), seed, suffix)
}

fn temporary(path: &Path) -> PathBuf {
    path.with_extension(format!("tmp.{}", std::process::id()))
}

fn read_header_bytes(path: &Path) -> io::Result<Vec<u8>> {
    let mut first = Vec::new();
    BufReader::new(File::open(path)?).read_until(b'\n', &mut first)?;
    if first.last() == Some(&b'\n') { first.pop(); }
    Ok(first)
}

fn selected_lags(output_dir: &Path, exp: &str, label: &str, contexts: &[Context]) -> io::Result<Vec<Option<usize>>> {
    let census_path = output_dir.parent().unwrap_or(output_dir).join("census/eligibility.json");
    let census: Value = serde_json::from_reader(File::open(census_path)?)?;
    let entries = census["training_contexts"].as_array().ok_or_else(|| io::Error::other("missing training census contexts"))?;
    contexts.iter().map(|c| {
        let map = serde_json::to_string(&json!({
            "raw_by_state": c.raw, "package_by_state": c.package
        }))?;
        let map_hash = format!("{:x}", Sha256::digest(format!("{map}\n").as_bytes()));
        let hits: Vec<&Value> = entries.iter().filter(|e| {
            e["exp"] == exp && e["config"] == label && e["k"] == c.k &&
            e["step_index"] == c.step_index && e["map_sha256"] == map_hash
        }).collect();
        if hits.len() != 1 { return Err(io::Error::other("Test B context absent or duplicated in census")); }
        Ok(hits[0]["h_c"].as_u64().map(|h| h as usize))
    }).collect()
}

pub fn write(
    kernel: &MarkovKernel,
    scan: &[ScaleScanEntry],
    seed: u64,
    exp: &str,
    label: &str,
    output_dir: &Path,
    phase: Phase,
    source_audit_dir: Option<&Path>,
) -> io::Result<()> {
    if matches!(phase, Phase::V6TrainVal | Phase::V6FreshTest) {
        let source = source_audit_dir.ok_or_else(|| io::Error::other("v6 requires the frozen audit-header directory"))?;
        return write_v6(kernel, scan, seed, exp, label, output_dir, phase, source);
    }
    fs::create_dir_all(output_dir)?;
    let stem = safe_stem(exp, label, seed);
    let audit_path = output_dir.join(format!("{stem}.audit.jsonl"));
    let record_path = output_dir.join(format!("{stem}.record.jsonl"));
    let audit_tmp = temporary(&audit_path);
    let record_tmp = temporary(&record_path);
    let contexts = context_maps(kernel, scan);
    let recipes: Vec<[usize; 3]> = (0..RECIPE_COUNT)
        .map(|a| [a % kernel.n, (a + 7) % kernel.n, (a + 19) % kernel.n])
        .collect();

    let record_contexts: Vec<Value> = contexts
        .iter()
        .map(|c| json!({
            "k": c.k, "step_index": c.step_index,
            "m": c.alphabet.len(), "alphabet_raw_package": c.alphabet
        }))
        .collect();
    let audit_header = frozen_audit_header(kernel, &contexts, seed, exp, label);
    let record_header = json!({
            "type": "header", "schema": "test_b_record_v1", "exp": exp,
            "config": label, "kernel_seed": seed, "contexts": record_contexts,
            "recipe_ids": (0..RECIPE_COUNT).collect::<Vec<_>>(),
            "path_steps": PATH_STEPS, "calibration_draws": CALIBRATION_DRAWS,
            "block_first": BLOCK_FIRST, "block_last": BLOCK_LAST,
            "replicates": REPLICATES
        });
    if let Phase::Complete = phase {
        if read_header_bytes(&audit_path)? != serde_json::to_vec(&audit_header)? ||
            read_header_bytes(&record_path)? != serde_json::to_vec(&record_header)? {
            return Err(io::Error::other("Test B kernel/lens header differs from census phase"));
        }
    }
    let mut audit = BufWriter::new(File::create(&audit_tmp)?);
    let mut record = BufWriter::new(File::create(&record_tmp)?);
    json_line(&mut audit, &audit_header)?;
    json_line(&mut record, &record_header)?;
    if let Phase::Header = phase {
        audit.flush()?;
        record.flush()?;
        drop(audit);
        drop(record);
        fs::rename(audit_tmp, audit_path)?;
        fs::rename(record_tmp, record_path)?;
        return Ok(());
    }

    // Calibration uses its own domain and never consumes a trajectory RNG.
    for (recipe, starts) in recipes.iter().enumerate() {
        let hash = digest(&calibration_domain(exp, label, seed, recipe));
        let mut rng = ChaCha8Rng::seed_from_u64(seed_at(&hash, 0));
        let states: Vec<usize> = (0..CALIBRATION_DRAWS)
            .map(|_| starts[rng.gen_range(0..3)])
            .collect();
        json_line(
            &mut audit,
            &json!({"type": "calibration", "recipe": recipe, "states": states}),
        )?;
        for c in &contexts {
            let labels: Vec<usize> = states.iter().map(|&s| c.joint[s]).collect();
            json_line(
                &mut record,
                &json!({
                    "type": "calibration", "k": c.k, "step_index": c.step_index,
                    "recipe": recipe, "labels": labels
                }),
            )?;
        }
    }

    // Generate each path once on the final K, then reuse it for every lens.
    let mut paths = Vec::with_capacity(
        (BLOCK_LAST - BLOCK_FIRST + 1) as usize * RECIPE_COUNT * REPLICATES,
    );
    for block in BLOCK_FIRST..=BLOCK_LAST {
        for (recipe, starts) in recipes.iter().enumerate() {
            for replicate in 0..REPLICATES {
                let hash = digest(&path_domain(exp, label, block, recipe, replicate));
                let mut start_rng = ChaCha8Rng::seed_from_u64(seed_at(&hash, 0));
                let start = starts[start_rng.gen_range(0..3)];
                let states = kernel.sample_trajectory(start, PATH_STEPS, seed_at(&hash, 8));
                if states.len() != PATH_STEPS + 1 {
                    return Err(io::Error::other("Test B sampler did not return 65 states"));
                }
                json_line(
                    &mut audit,
                    &json!({
                        "type": "path", "block": block, "recipe": recipe,
                        "replicate": replicate, "states": states
                    }),
                )?;
                paths.push(PathRow {
                    block,
                    recipe,
                    replicate,
                    states,
                });
            }
        }
    }
    let lags = if let Phase::Complete = phase {
        selected_lags(output_dir, exp, label, &contexts)?
    } else { vec![None; contexts.len()] };
    for (c, selected_h) in contexts.iter().zip(lags) {
        for p in &paths {
            let labels: Vec<usize> = p.states.iter().map(|&s| c.joint[s]).collect();
            let readings: Vec<usize> = match selected_h {
                Some(h) => (0..=8).map(|t| labels[t * h]).collect(),
                None => labels.clone(),
            };
            json_line(
                &mut record,
                &json!({
                    "type": "path", "k": c.k, "step_index": c.step_index,
                    "block": p.block, "recipe": p.recipe,
                    "replicate": p.replicate, "selected_h": selected_h,
                    "trajectory_id": format!("{}:{}:{}:{}:{}", exp, label, p.block, p.recipe, p.replicate),
                    "split": if p.block <= 910010 && p.recipe < 12 { "train" }
                        else if (910011..=910015).contains(&p.block) && (12..18).contains(&p.recipe) { "validation" }
                        else if p.block >= 910016 && p.recipe >= 18 { "test" }
                        else { "unused_cross_split" },
                    "labels": readings
                }),
            )?;
        }
    }
    audit.flush()?;
    record.flush()?;
    drop(audit);
    drop(record);
    fs::rename(audit_tmp, audit_path)?;
    fs::rename(record_tmp, record_path)?;
    Ok(())
}

// V6 is isolated below this point. The v4/v5 export path above is unchanged.
#[derive(serde::Deserialize, serde::Serialize)]
struct V6Recipe {
    states: [usize; 3],
    weights_num: [usize; 3],
    denominator: usize,
}

fn v6_start(recipe: &V6Recipe, rng: &mut ChaCha8Rng, n: usize) -> io::Result<usize> {
    if recipe.denominator == 0 || recipe.weights_num.iter().sum::<usize>() != recipe.denominator
        || recipe.states.iter().any(|&state| state >= n)
        || recipe.weights_num.iter().any(|&weight| weight == 0)
    {
        return Err(io::Error::other("invalid v6 recipe"));
    }
    let draw = rng.gen_range(0..recipe.denominator);
    let mut cumulative = 0;
    for (&state, &weight) in recipe.states.iter().zip(&recipe.weights_num) {
        cumulative += weight;
        if draw < cumulative { return Ok(state); }
    }
    Err(io::Error::other("v6 recipe sample outside support"))
}

fn frozen_audit_header(kernel: &MarkovKernel, contexts: &[Context], seed: u64, exp: &str, label: &str) -> Value {
    let recipes: Vec<[usize; 3]> = (0..RECIPE_COUNT)
        .map(|a| [a % kernel.n, (a + 7) % kernel.n, (a + 19) % kernel.n])
        .collect();
    let audit_contexts: Vec<Value> = contexts.iter().map(|c| json!({
        "k": c.k, "step_index": c.step_index, "raw_by_state": c.raw,
        "package_by_state": c.package, "joint_by_state": c.joint,
        "alphabet_raw_package": c.alphabet
    })).collect();
    json!({
            "type": "header", "schema": "test_b_audit_v1", "exp": exp,
            "config": label, "kernel_seed": seed, "n": kernel.n,
            "kernel": kernel.kernel, "contexts": audit_contexts,
            "recipes": recipes, "path_steps": PATH_STEPS,
            "calibration_draws": CALIBRATION_DRAWS,
            "block_first": BLOCK_FIRST, "block_last": BLOCK_LAST,
            "replicates": REPLICATES,
            "seed_rule": "SHA256 UTF8 TestB/v4/{Y0cal|path}/(EXP::label,seed-or-block,recipe[,replicate]); first 8 bytes LE for calibration/start, bytes 8..16 LE for transition"
        })
}

fn v6_source_header(
    kernel: &MarkovKernel, contexts: &[Context], seed: u64, exp: &str, label: &str,
    source_audit_dir: &Path,
) -> io::Result<String> {
    let path = source_audit_dir.join(format!("{}.audit.jsonl", safe_stem(exp, label, seed)));
    let bytes = read_header_bytes(&path)?;
    let expected = serde_json::to_vec(&frozen_audit_header(kernel, contexts, seed, exp, label))?;
    if bytes != expected {
        return Err(io::Error::other("v6 kernel/lens header bytes differ from frozen audit header"));
    }
    Ok(format!("{:x}", Sha256::digest(bytes)))
}

fn v6_recipes(
    output_dir: &Path, exp: &str, label: &str, source_hash: &str,
) -> io::Result<Vec<V6Recipe>> {
    let census_path = output_dir.parent().unwrap_or(output_dir).join("census/eligibility.json");
    let census: Value = serde_json::from_reader(File::open(census_path)?)?;
    if census["schema"] != "test_b_v6_census_release_v1"
        || census["spec_sha256"] != "3abc68c6f0a8070240a2302434b28644fbf8b67f955a65af2cf33667cfd6d2cd"
    {
        return Err(io::Error::other("wrong v6 census release"));
    }
    let units = census["units"].as_array().ok_or_else(|| io::Error::other("missing v6 census units"))?;
    let matches: Vec<&Value> = units.iter().filter(|unit| unit["exp"] == exp && unit["config"] == label).collect();
    if matches.len() != 1 || matches[0]["sealed_kernel_header_sha256"] != source_hash {
        return Err(io::Error::other("v6 census source header mismatch"));
    }
    let recipe_path = output_dir.parent().unwrap_or(output_dir).join("census/sealed/recipe_audit.jsonl");
    let recipe_bytes = fs::read(recipe_path)?;
    if census["sealed_recipe_audit_sha256"] != format!("{:x}", Sha256::digest(&recipe_bytes)) {
        return Err(io::Error::other("v6 sealed recipe audit hash differs from census"));
    }
    let recipe_rows: Vec<Value> = recipe_bytes.split(|&byte| byte == b'\n')
        .filter(|line| !line.is_empty())
        .map(serde_json::from_slice).collect::<Result<_, _>>()?;
    let matched: Vec<&Value> = recipe_rows.iter().filter(|row| row["exp"] == exp && row["config"] == label
        && row["sealed_kernel_header_sha256"] == source_hash).collect();
    if matched.len() != 1 { return Err(io::Error::other("v6 recipe audit unit missing or duplicated")); }
    let recipes: Vec<V6Recipe> = serde_json::from_value(matched[0]["recipes"].clone())?;
    if recipes.len() != 60 { return Err(io::Error::other("v6 census recipe count differs from spec")); }
    Ok(recipes)
}

fn write_v6(
    kernel: &MarkovKernel, scan: &[ScaleScanEntry], seed: u64, exp: &str, label: &str,
    output_dir: &Path, phase: Phase, source_audit_dir: &Path,
) -> io::Result<()> {
    if seed != 910000 { return Err(io::Error::other("v6 must reuse fixed kernel seed 910000")); }
    fs::create_dir_all(output_dir)?;
    let contexts = context_maps(kernel, scan);
    write_v6_contexts(kernel, &contexts, seed, exp, label, output_dir, phase, source_audit_dir)
}

fn write_v6_contexts(
    kernel: &MarkovKernel, contexts: &[Context], seed: u64, exp: &str, label: &str,
    output_dir: &Path, phase: Phase, source_audit_dir: &Path,
) -> io::Result<()> {
    fs::create_dir_all(output_dir)?;
    let source_hash = v6_source_header(kernel, contexts, seed, exp, label, source_audit_dir)?;
    let recipes = v6_recipes(output_dir, exp, label, &source_hash)?;
    let lags = selected_lags(output_dir, exp, label, &contexts)?;
    let stem = safe_stem(exp, label, seed);
    let tag = match phase {
        Phase::V6TrainVal => "v6.trainval",
        Phase::V6FreshTest => "v6.fresh_test",
        _ => return Err(io::Error::other("invalid v6 sidecar phase")),
    };
    let audit_path = output_dir.join(format!("{stem}.{tag}.audit.jsonl"));
    let record_path = output_dir.join(format!("{stem}.{tag}.record.jsonl"));
    if audit_path.exists() || record_path.exists() {
        return Err(io::Error::other("v6 sidecar output already exists"));
    }
    let audit_contexts: Vec<Value> = contexts.iter().map(|c| json!({
        "k": c.k, "step_index": c.step_index, "raw_by_state": c.raw,
        "package_by_state": c.package, "joint_by_state": c.joint,
        "alphabet_raw_package": c.alphabet
    })).collect();
    let record_contexts: Vec<Value> = contexts.iter().zip(&lags).map(|(c,h)| json!({
        "k": c.k, "step_index": c.step_index, "m": c.alphabet.len(),
        "selected_h": h, "alphabet_raw_package": c.alphabet
    })).collect();
    let mode = match phase { Phase::V6TrainVal => "trainval", _ => "fresh_test" };
    let audit_header = json!({
        "type": "header", "schema": "test_b_v6_audit_v1", "mode": mode,
        "exp": exp, "config": label, "kernel_seed": seed, "n": kernel.n,
        "source_header_sha256": source_hash, "kernel": kernel.kernel,
        "contexts": audit_contexts, "recipes": recipes, "recipe_count": 60, "path_steps": 64,
        "calibration_draws": 8192,
        "seed_rule": "SHA256 UTF8 TestB/v6/Y0cal/(kernel-header-hash,recipe) and TestB/v6/path/(kernel-header-hash,block,recipe,replicate); first 8 bytes LE for calibration/start, bytes 8..16 LE for transition"
    });
    let record_header = json!({
        "type": "header", "schema": "test_b_v6_record_v1", "mode": mode,
        "exp": exp, "config": label, "kernel_seed": seed,
        "source_header_sha256": source_hash, "contexts": record_contexts,
        "recipe_ids": (0..60).collect::<Vec<_>>(), "path_steps": 64,
        "calibration_draws": 8192
    });
    if matches!(phase, Phase::V6FreshTest) {
        let previous_audit = output_dir.join(format!("{stem}.v6.trainval.audit.jsonl"));
        let previous_record = output_dir.join(format!("{stem}.v6.trainval.record.jsonl"));
        let mut expected_audit = audit_header.clone();
        let mut expected_record = record_header.clone();
        expected_audit["mode"] = json!("trainval");
        expected_record["mode"] = json!("trainval");
        if read_header_bytes(&previous_audit)? != serde_json::to_vec(&expected_audit)?
            || read_header_bytes(&previous_record)? != serde_json::to_vec(&expected_record)?
        {
            return Err(io::Error::other("v6 fresh-test kernel/lens header differs from trainval"));
        }
    }
    let audit_tmp = temporary(&audit_path);
    let record_tmp = temporary(&record_path);
    let mut audit = BufWriter::new(File::create_new(&audit_tmp)?);
    let mut record = BufWriter::new(File::create_new(&record_tmp)?);
    json_line(&mut audit, &audit_header)?;
    json_line(&mut record, &record_header)?;
    if matches!(phase, Phase::V6TrainVal) {
        for (recipe, mix) in recipes.iter().enumerate() {
            let domain = format!("TestB/v6/Y0cal/({source_hash},{recipe})");
            let hash = digest(&domain);
            let mut rng = ChaCha8Rng::seed_from_u64(seed_at(&hash, 0));
            let mut states = Vec::with_capacity(8192);
            for _ in 0..8192 { states.push(v6_start(mix, &mut rng, kernel.n)?); }
            json_line(&mut audit, &json!({"type": "calibration", "recipe": recipe, "states": states}))?;
            for c in contexts {
                let labels: Vec<usize> = states.iter().map(|&state| c.joint[state]).collect();
                json_line(&mut record, &json!({
                    "type": "calibration", "k": c.k, "step_index": c.step_index,
                    "recipe": recipe, "labels": labels
                }))?;
            }
        }
    }
    let cells: Vec<(u64, usize)> = if matches!(phase, Phase::V6TrainVal) {
        (910001..=910010).flat_map(|b| (0..36).map(move |a| (b,a)))
            .chain((910011..=910015).flat_map(|b| (36..48).map(move |a| (b,a))))
            .collect()
    } else {
        (910036..=910055).flat_map(|b| (48..60).map(move |a| (b,a))).collect()
    };
    for (block, recipe) in cells {
        for replicate in 0..REPLICATES {
            let domain = format!("TestB/v6/path/({source_hash},{block},{recipe},{replicate})");
            let hash = digest(&domain);
            let mut start_rng = ChaCha8Rng::seed_from_u64(seed_at(&hash, 0));
            let start = v6_start(&recipes[recipe], &mut start_rng, kernel.n)?;
            let states = kernel.sample_trajectory(start, PATH_STEPS, seed_at(&hash, 8));
            if states.len() != 65 { return Err(io::Error::other("v6 sampler did not return 65 states")); }
            json_line(&mut audit, &json!({
                "type": "path", "block": block, "recipe": recipe,
                "replicate": replicate, "states": states
            }))?;
            for (c, selected_h) in contexts.iter().zip(&lags) {
                if let Some(h) = selected_h {
                    let labels: Vec<usize> = (0..=8).map(|t| c.joint[states[t * h]]).collect();
                    json_line(&mut record, &json!({
                        "type": "path", "k": c.k, "step_index": c.step_index,
                        "block": block, "recipe": recipe, "replicate": replicate,
                        "selected_h": h, "split": if block <= 910010 { "train" }
                            else if block <= 910015 { "validation" } else { "test" },
                        "trajectory_id": format!("{}:{}:{}:{}:{}", exp, label, block, recipe, replicate),
                        "labels": labels
                    }))?;
                }
            }
        }
    }
    audit.flush()?;
    record.flush()?;
    drop(audit);
    drop(record);
    fs::rename(audit_tmp, audit_path)?;
    fs::rename(record_tmp, record_path)?;
    Ok(())
}

/// Replay only registered train/validation samples from an exported final header.
/// No dynamics, spectral reconstruction, or additional random draws are run.
pub fn sample_trainval_header(header_path: &Path, output_dir: &Path) -> io::Result<()> {
    sample_header(header_path, output_dir, Phase::V6TrainVal)
}

/// Locked samples use the identical historical RNG/sampling body. The public
/// coordinator checks committed predictions and margins before this call.
pub fn sample_locked_header(header_path: &Path, output_dir: &Path) -> io::Result<()> {
    sample_header(header_path, output_dir, Phase::V6FreshTest)
}

fn sample_header(header_path: &Path, output_dir: &Path, phase: Phase) -> io::Result<()> {
    let bytes = read_header_bytes(header_path)?;
    let h: Value = serde_json::from_slice(&bytes)?;
    if h["schema"] != "test_b_audit_v1" || h["kernel_seed"] != 910000 {
        return Err(io::Error::other("registered seed-910000 kernel header required"));
    }
    let kernel: MarkovKernel = serde_json::from_value(json!({"n": h["n"], "kernel": h["kernel"]}))?;
    if kernel.n < 3 || kernel.kernel.len() != kernel.n || kernel.kernel.iter().any(|r| r.len() != kernel.n
        || r.iter().any(|x| !x.is_finite() || *x < 0.) || (r.iter().sum::<f64>()-1.).abs() > 1e-10) {
        return Err(io::Error::other("invalid captured kernel"));
    }
    let fields = h["contexts"].as_array().ok_or_else(|| io::Error::other("missing contexts"))?;
    let contexts = fields.iter().map(|c| -> io::Result<Context> {
        Ok(Context { k: serde_json::from_value(c["k"].clone())?,
            step_index: serde_json::from_value(c["step_index"].clone())?,
            raw: serde_json::from_value(c["raw_by_state"].clone())?,
            package: serde_json::from_value(c["package_by_state"].clone())?,
            joint: serde_json::from_value(c["joint_by_state"].clone())?,
            alphabet: serde_json::from_value(c["alphabet_raw_package"].clone())? })
    }).collect::<io::Result<Vec<_>>>()?;
    for c in &contexts {
        if c.raw.len()!=kernel.n || c.package.len()!=kernel.n || c.joint.len()!=kernel.n
            || c.joint.iter().enumerate().any(|(i, &j)| c.alphabet.get(j) != Some(&(c.raw[i],c.package[i]))) {
            return Err(io::Error::other("inconsistent captured joint labels"));
        }
    }
    let exp = h["exp"].as_str().ok_or_else(|| io::Error::other("missing experiment"))?;
    let label = h["config"].as_str().ok_or_else(|| io::Error::other("missing configuration"))?;
    let source = header_path.parent().ok_or_else(|| io::Error::other("header has no parent"))?;
    write_v6_contexts(&kernel, &contexts, 910000, exp, label, output_dir, phase, source)
}

#[cfg(test)]
mod v6_tests {
    use super::*;

    #[test]
    fn v6_exact_header_rejects_kernel_ulp_and_lens_changes() {
        let root = std::env::temp_dir().join(format!("testb-header-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let kernel = MarkovKernel { n: 2, kernel: vec![vec![0.25, 0.75], vec![0.5, 0.5]] };
        let mut contexts = vec![Context { k: 2, step_index: 0, raw: vec![0, 1],
            package: vec![0, 1], joint: vec![0, 1], alphabet: vec![(0, 0), (1, 1)] }];
        let bytes = serde_json::to_vec(&frozen_audit_header(&kernel, &contexts, 910000, "test", "unit")).unwrap();
        let path = root.join(format!("{}.audit.jsonl", safe_stem("test", "unit", 910000)));
        fs::write(&path, [bytes.as_slice(), b"\n"].concat()).unwrap();
        assert_eq!(v6_source_header(&kernel, &contexts, 910000, "test", "unit", &root).unwrap(),
                   format!("{:x}", Sha256::digest(&bytes)));
        for value in [0.3, f64::from_bits(0.25f64.to_bits() + 1)] {
            let mut changed = kernel.clone(); changed.kernel[0][0] = value;
            assert!(v6_source_header(&changed, &contexts, 910000, "test", "unit", &root).is_err());
        }
        contexts[0].raw[0] = 1;
        assert!(v6_source_header(&kernel, &contexts, 910000, "test", "unit", &root).is_err());
        contexts[0].raw[0] = 0; contexts[0].alphabet[0] = (1, 0);
        assert!(v6_source_header(&kernel, &contexts, 910000, "test", "unit", &root).is_err());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn v6_accepts_all_frozen_audit_headers() {
        let Some(root) = std::env::var_os("TESTB_FROZEN_AUDIT_DIR") else { return; };
        let root = PathBuf::from(root);
        let mut count = 0;
        for item in fs::read_dir(&root).unwrap() {
            let path = item.unwrap().path();
            if !path.to_string_lossy().ends_with(".audit.jsonl") { continue; }
            let bytes = read_header_bytes(&path).unwrap();
            let text = std::str::from_utf8(&bytes).unwrap();
            let header: Value = serde_json::from_slice(&bytes).unwrap();
            let n = header["n"].as_u64().unwrap() as usize;
            // Test fixture only: Rust's f64 parser recovers the serialized bits.
            // Production never parses/replaces kernel floats or frozen bytes.
            let start = text.find("\"kernel\":[").unwrap() + "\"kernel\":".len();
            let end = text[start..].find(",\"kernel_seed\":").unwrap() + start;
            let values: Vec<f64> = text[start..end].split(|c| c == '[' || c == ']' || c == ',')
                .filter(|s| !s.is_empty()).map(|s| s.parse().unwrap()).collect();
            assert_eq!(values.len(), n*n);
            let kernel = MarkovKernel { n, kernel: values.chunks(n).map(|x| x.to_vec()).collect() };
            let ids = |v: &Value| v.as_array().unwrap().iter().map(|x| x.as_u64().unwrap() as usize).collect();
            let contexts: Vec<Context> = header["contexts"].as_array().unwrap().iter().map(|c| Context {
                k: c["k"].as_u64().unwrap() as usize, step_index: c["step_index"].as_u64().unwrap() as usize,
                raw: ids(&c["raw_by_state"]), package: ids(&c["package_by_state"]), joint: ids(&c["joint_by_state"]),
                alphabet: c["alphabet_raw_package"].as_array().unwrap().iter().map(|x|
                    (x[0].as_u64().unwrap() as usize, x[1].as_u64().unwrap() as usize)).collect(),
            }).collect();
            assert_eq!(v6_source_header(&kernel, &contexts, header["kernel_seed"].as_u64().unwrap(),
                header["exp"].as_str().unwrap(), header["config"].as_str().unwrap(), &root).unwrap(),
                format!("{:x}", Sha256::digest(&bytes)));
            count += 1;
        }
        assert_eq!(count, 140);
    }

    #[test]
    fn v6_modes_are_explicit_and_weighted_calibration_replays() {
        assert!(matches!(Phase::parse("v6-trainval"), Some(Phase::V6TrainVal)));
        assert!(matches!(Phase::parse("v6-fresh-test"), Some(Phase::V6FreshTest)));
        assert!(matches!(Phase::parse("full"), Some(Phase::Full)));
        let recipe = V6Recipe { states: [1, 3, 5], weights_num: [2, 3, 5], denominator: 10 };
        let hash = digest("TestB/v6/Y0cal/(synthetic-header,0)");
        let draw = || {
            let mut rng = ChaCha8Rng::seed_from_u64(seed_at(&hash, 0));
            (0..256).map(|_| v6_start(&recipe, &mut rng, 6).unwrap()).collect::<Vec<_>>()
        };
        assert_eq!(draw(), draw());
        assert!(draw().iter().all(|state| [1, 3, 5].contains(state)));
    }
}
