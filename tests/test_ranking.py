import pytest
from app.services.conocimiento.busqueda_hibrida import fusionar_rankings


def test_rrf_favorece_acuerdo_y_es_simetrico():
    rankings = [["a", "b", "c"], ["d", "b", "e"]]
    result = fusionar_rankings(rankings)
    assert result[0][0] == "b"
    assert result[0][1] == pytest.approx(2/62)
    assert result == fusionar_rankings(list(reversed(rankings)))


def test_desempate_estable_vacios_duplicados():
    assert fusionar_rankings([[], []]) == []
    assert fusionar_rankings([["b"], ["a"]])[0][0] == "a"
    assert dict(fusionar_rankings([["a", "a"]]))["a"] == 1/61
    with pytest.raises(ValueError):
        fusionar_rankings([["a"]], 0)
