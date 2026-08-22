from moneymaker.ev import bucket_probs, expected_value

def test_probs_sum_to_one():
    p = bucket_probs(.03, .12, .22, .40, .74)
    assert abs(p.sum() - 1) < 1e-9

def test_no_cut_floor():
    row = dict(win=.02, top_5=.09, top_10=.18, top_20=.33, make_cut=.70)
    assert expected_value(row, 20e6, has_cut=False) > \
           expected_value(row, 20e6, has_cut=True)
