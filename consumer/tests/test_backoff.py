"""
Pruebas de la función de backoff exponencial con jitter, aisladas del resto
de la política de reintentos (ver app/retry.py::calcular_espera).
"""
from app.retry import calcular_espera


def test_espera_crece_exponencialmente_con_el_numero_de_intento() -> None:
    """
    El TECHO de la espera (el máximo posible, antes del sorteo aleatorio)
    debe duplicarse en cada intento: es la propiedad que distingue un backoff
    exponencial de uno lineal o constante.
    """
    base = 1.0
    techos = [base * (2 ** (intento - 1)) for intento in range(1, 5)]

    assert techos == [1.0, 2.0, 4.0, 8.0]


def test_espera_nunca_es_negativa_ni_supera_el_techo(monkeypatch) -> None:
    base_s = 0.5
    for intento in range(1, 6):
        for _ in range(50):  # múltiples muestras: random.uniform es estocástico
            espera = calcular_espera(intento, base_s)
            techo = base_s * (2 ** (intento - 1))
            assert 0.0 <= espera <= techo


def test_jitter_produce_valores_distintos_entre_llamadas() -> None:
    """
    Verifica que efectivamente hay aleatoriedad (no un valor fijo): es lo que
    evita que múltiples clientes reintenten exactamente en el mismo instante
    (ver docstring de calcular_espera sobre "thundering herd").
    """
    valores = {calcular_espera(intento=3, base_s=1.0) for _ in range(30)}

    assert len(valores) > 1
