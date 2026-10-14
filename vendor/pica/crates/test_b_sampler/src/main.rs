//! Captured-kernel sampling; locked opening requires committed numeric files.
#[allow(dead_code)]
#[path = "../../runner/src/test_b_sidecar.rs"]
mod test_b_sidecar;
use clap::Parser;
use std::path::PathBuf;

#[derive(Parser)]
struct Args {
    #[arg(long)] header: PathBuf,
    #[arg(long)] output: PathBuf,
    #[arg(long, requires = "predictions_root")] locked_test: bool,
    #[arg(long, requires = "locked_test")] predictions_root: Option<PathBuf>,
}
fn main() {
    let args = Args::parse();
    let result = if args.locked_test {
        check_predictions(args.predictions_root.as_ref().unwrap())
            .and_then(|_| test_b_sidecar::sample_locked_header(&args.header, &args.output))
    } else { test_b_sidecar::sample_trainval_header(&args.header, &args.output) };
    if let Err(error) = result {
        eprintln!("Test B sampling failed: {error}");
        std::process::exit(1);
    }
}

fn check_predictions(root: &std::path::Path) -> std::io::Result<()> {
    use sha2::{Digest, Sha256};
    use std::io::{Error, ErrorKind};
    let seal: serde_json::Value = serde_json::from_slice(&std::fs::read(root.join("prediction_seal_manifest.json"))?)?;
    if seal["locked_test_sampled_or_opened"] != false {
        return Err(Error::new(ErrorKind::InvalidData, "prediction commitment required"));
    }
    let files = seal["files"].as_object().ok_or_else(|| Error::other("missing committed numeric files"))?;
    if !files.contains_key("fits/rank_margins.json") || !files.keys().any(|p| p.ends_with("/predictions.json")) {
        return Err(Error::other("committed predictions and margins required"));
    }
    for (name, digest) in files {
        let relative = std::path::Path::new(name);
        if relative.is_absolute() || relative.components().any(|c| matches!(c, std::path::Component::ParentDir)) {
            return Err(Error::other("committed file escapes prediction root"));
        }
        let path=root.join(relative);
        if !path.canonicalize()?.starts_with(root.canonicalize()?) { return Err(Error::other("committed symlink escapes root")); }
        let actual=format!("{:x}", Sha256::digest(std::fs::read(path)?));
        if digest.as_str()!=Some(&actual) { return Err(Error::other("committed numeric file changed")); }
    }
    Ok(())
}
