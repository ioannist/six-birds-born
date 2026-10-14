"""Registered diagnostic arithmetic; no refitting, sampling or gate changes."""


def candidate_counts(product_labels):
    candidates = (1 << (product_labels-1)) * 76
    return {'rank_two_sign_patterns': 1 << (product_labels-1),
            'rank_two_scored_candidates': candidates,
            'candidate_theta_arrays_bytes_alone': candidates * (2*product_labels+4) * 8}


def diagnostics(entries, alphabet_for_entry):
    figures=[];seen=set()
    for entry,_ in entries:
        if entry['file'] in seen:continue
        seen.add(entry['file'])
        alphabet=alphabet_for_entry(entry)
        raw_m=len({row[0] for row in alphabet});package_m=len({row[1] for row in alphabet})
        product_labels=raw_m*package_m
        if product_labels<1:raise ValueError('erasure diagnostic requires nonempty raw/package alphabets')
        figures.append({'context_file':entry['file'],'original_labels':entry['m'],
            'raw_labels':raw_m,'package_labels':package_m,'full_product_labels':product_labels,
            **candidate_counts(product_labels)})
    # Twenty-label reference from the effective protocol; compute its estimates
    # with the same formula as the campaign contexts.
    reference=candidate_counts(20);reference.pop('rank_two_sign_patterns')
    return {'status':'NOT_COMPUTED','diagnostic_only':True,'refits':0,
            'changes_gate_or_verdict':False,'campaign_context_figures':figures,
            'subset_infeasibility_reference':{'product_labels':20,**reference}}
