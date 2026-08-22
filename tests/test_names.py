from moneymaker.names import norm

def test_last_first():
    assert norm("H\u00f8jgaard, Rasmus") == "rasmus hojgaard"

def test_paren():
    assert norm("Collin Morikawa (WD)") == "collin morikawa"

def test_amateur():
    assert norm("Koivun, Jackson (a)") == "jackson koivun"

def test_accents():
    assert norm("\u00c5berg, Ludvig") == "ludvig aberg"

def test_kims_differ():
    assert norm("Kim, Si Woo") != norm("Kim, Tom")
