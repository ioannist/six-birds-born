
// Read-only access to the unchanged private routine, as in the historical
// scratch/arch_probes/prepare_join.py wrapper. No runner or sampler is invoked.
pub fn replay_context_maps(kernel: &MarkovKernel, k: usize) -> Value {
    let scan = [ScaleScanEntry {
        k, macro_gap:None, frob:None, sigma_pi:None, max_asym:None,
        cyc_mean:None, cyc_max:None, n_chiral:None, step_entropy:None,
        pla2_gap:None, lagr_geo_r2:None, lagr_diff_kl:None, lagr_diff_alpha:None,
        t_rel:None, gap_ratio:None, eigen_entropy:None, spectral_participation:None,
        slow_modes_r50:None, slow_modes_r70:None, slow_modes_r90:None,
        nontrivial_eigenvalues:None
    }];
    let c = context_maps(kernel, &scan).remove(0);
    json!({"raw":c.raw, "package":c.package, "joint":c.joint})
}
