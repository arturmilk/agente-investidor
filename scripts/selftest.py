"""Autoteste do Agente Bolsa — valida fórmulas e o mapeamento das contas da CVM.

Uso:
    python selftest.py            # testes offline (segundos, sem internet)
    python selftest.py --online   # + análise real de 1 ticker (baixa dados da CVM na 1ª vez)
"""
from __future__ import annotations

import math
import sys
import unittest

import cvm
import indicators as ind
import report
import scoring
import valuation as val


def _emp(anual, ttm, acoes=None, info=None):
    return {"anual": anual, "ttm": ttm, "ttm_info": info or {"tipo": "ttm", "ref": "2026-06-30"},
            "acoes": acoes, "acoes_hist": {}, "trimestre": None}


def _ano(ano, **kw):
    base = {"dt_fim": f"{ano}-12-31", "receita": 100.0, "lucro_bruto": 40.0, "ebit": 20.0, "depreciacao": 5.0,
            "lucro_liquido": 12.0, "ativo_total": 200.0, "ativo_circulante": 80.0, "passivo_circulante": 50.0,
            "pl": 100.0, "emprestimos_lp": 30.0, "emprestimos_cp": 10.0, "caixa": 15.0, "fco": 18.0,
            "capex": 6.0, "dividendos_pagos": 5.0, "emissao_acoes": 0.0, "layout": "geral"}
    base.update(kw)
    return base


class Contas(unittest.TestCase):
    def test_dre_industrial(self):
        a = {"3.01": ("receita de venda de bens e/ou servicos", 1000.0), "3.03": ("resultado bruto", 400.0),
             "3.05": ("resultado antes do resultado financeiro e dos tributos", 200.0),
             "3.06": ("resultado financeiro", -50.0), "3.06.02": ("despesas financeiras", -80.0),
             "3.07": ("resultado antes dos tributos sobre o lucro", 150.0),
             "3.08": ("imposto de renda e contribuicao social sobre o lucro", -45.0),
             "3.09": ("resultado liquido das operacoes continuadas", 105.0),
             "3.11": ("lucro/prejuizo consolidado do periodo", 105.0),
             "3.11.01": ("atribuido a socios da empresa controladora", 100.0),
             "3.11.02": ("atribuido a socios nao controladores", 5.0)}
        o = cvm._dre(a)
        self.assertEqual((o["receita"], o["ebit"], o["lair"], o["ir"]), (1000.0, 200.0, 150.0, -45.0))
        self.assertEqual((o["lucro_liquido"], o["lucro_controladora"], o["despesas_financeiras"]), (105.0, 100.0, -80.0))

    def test_dre_banco(self):
        a = {"3.01": ("receitas de intermediacao financeira", 300.0),
             "3.05": ("resultado antes dos tributos sobre o lucro", 50.0),
             "3.06": ("imposto de renda e contribuicao social sobre o lucro", -10.0),
             "3.07": ("lucro ou prejuizo das operacoes continuadas", 40.0),
             "3.09": ("lucro ou prejuizo antes das participacoes e contribuicoes estatutarias", 40.0),
             "3.11": ("lucro ou prejuizo liquido consolidado do periodo", 40.0),
             "3.11.01": ("atribuido aos socios da empresa controladora", 38.0)}
        o = cvm._dre(a)
        self.assertIsNone(o.get("ebit"))
        self.assertEqual((o["lair"], o["lucro_liquido"], o["lucro_controladora"]), (50.0, 40.0, 38.0))

    def test_bpp_e_dfc(self):
        bpp = cvm._bpp({"2": ("passivo total", 500.0), "2.01": ("passivo circulante", 100.0),
                        "2.01.04": ("emprestimos e financiamentos", 30.0),
                        "2.02": ("passivo nao circulante", 150.0), "2.02.01": ("emprestimos e financiamentos", 90.0),
                        "2.03": ("patrimonio liquido consolidado", 250.0),
                        "2.03.04": ("reservas de lucros", 60.0),
                        "2.03.09": ("participacao dos acionistas nao controladores", 10.0)})
        self.assertEqual((bpp["pl"], bpp["minoritarios"], bpp["pl_controladora"]), (250.0, 10.0, 240.0))
        self.assertEqual((bpp["emprestimos_cp"], bpp["emprestimos_lp"], bpp["reservas_lucros"]), (30.0, 90.0, 60.0))
        dfc = cvm._dfc({"6.01": ("caixa liquido atividades operacionais", 120.0),
                        "6.01.01.02": ("depreciacao, amortizacao e exaustao", 25.0),
                        "6.01.01.05": ("amortizacao de custos de captacao", 3.0),
                        "6.02": ("caixa liquido atividades de investimento", -60.0),
                        "6.02.01": ("aquisicao de imobilizado", -40.0),
                        "6.02.02": ("recebimento na venda de ativo imobilizado", 5.0),
                        "6.02.03": ("intangivel", -8.0),
                        "6.03": ("caixa liquido atividades de financiamento", -30.0),
                        "6.03.02": ("pagamento de dividendos e juros sobre capital proprio", -20.0),
                        "6.03.03": ("dividendos pagos a acionistas nao controladores", -4.0),
                        "6.03.04": ("aumento de capital", 7.0),
                        "6.03.05": ("emissao de debentures", 50.0)})
        self.assertEqual((dfc["depreciacao"], dfc["capex"], dfc["dividendos_pagos"], dfc["emissao_acoes"]),
                         (25.0, 48.0, 20.0, 7.0))

    def test_ttm(self):
        hist = {"2025-12-31": {"dt_fim": "2025-12-31", "lucro_liquido": 100.0, "receita": 1000.0, "pl": 500.0}}
        itr = {"dt_refer": "2026-06-30", "ytd": {"dt_ini": "2026-01-01", "lucro_liquido": 60.0, "receita": 520.0},
               "ytd_ant": {"dt_ini": "2025-01-01", "lucro_liquido": 45.0, "receita": 480.0},
               "bal": {"pl": 540.0}}
        t, info = cvm._ttm(hist, itr)
        self.assertEqual((t["lucro_liquido"], t["receita"], t["pl"], info["tipo"]), (115.0, 1040.0, 540.0, "ttm"))


class Formulas(unittest.TestCase):
    def test_cagr_tendencia(self):
        s = [("2021", 100.0), ("2022", 110.0), ("2023", 121.0), ("2024", 133.1), ("2025", 146.41)]
        self.assertAlmostEqual(ind.cagr(s), 0.10, places=6)
        self.assertAlmostEqual(ind.tendencia(s), 0.10, places=6)
        self.assertIsNone(ind.cagr([("2024", -1.0), ("2025", 5.0), ("2023", 3.0)]))

    def test_graham_bazin(self):
        m = {"lpa": 2.0, "vpa": 10.0, "preco": 15.0, "pl": 7.5, "pvp": 1.5, "market_cap": 3e9,
             "dpa_mediano_5a": 1.2, "dy_mediano_5a": 0.08, "anos_com_dividendos_5a": 5, "dl_pl": 0.5,
             "anos_lucro_positivo_5a": 5, "financeiro": False, "liquidez_corrente": 1.6}
        g = val.graham(m, {str(a): _ano(a) for a in range(2021, 2026)})
        self.assertAlmostEqual(g["valor_justo"], math.sqrt(22.5 * 2 * 10), places=6)
        self.assertAlmostEqual(g["margem"], math.sqrt(450) / 15 - 1, places=6)
        b = val.bazin(m)
        self.assertAlmostEqual(b["preco_teto"], 20.0, places=6)
        self.assertEqual(b["atendidos"], 4)

    def test_piotroski(self):
        anual = {"2024": _ano(2024, lucro_liquido=8.0, fco=10.0, ativo_total=210.0, emprestimos_lp=40.0,
                              ativo_circulante=70.0, lucro_bruto=35.0, receita=95.0, _acoes=100.0),
                 "2025": _ano(2025, lucro_liquido=12.0, fco=18.0, ativo_total=200.0, emprestimos_lp=30.0,
                              ativo_circulante=80.0, lucro_bruto=40.0, receita=100.0, _acoes=100.0)}
        f = val.piotroski(anual)
        self.assertEqual((f["score"], f["avaliados"]), (9, 9))

    def test_altman(self):
        z = val.altman_z2(_ano(2025, reservas_lucros=40.0, lucros_acumulados=0.0))
        x1, x2, x3, x4 = 30 / 200, 40 / 200, 20 / 200, 100 / 100
        self.assertAlmostEqual(z["z"], 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4, places=6)
        self.assertEqual(z["zona"], "segura")

    def test_pvp_justo(self):
        self.assertAlmostEqual(val.pvp_justo_roe(0.20, 0.19, 0.04), 0.16 / 0.15, places=6)
        self.assertIsNone(val.pvp_justo_roe(0.03, 0.19, 0.04))


class Mercado(unittest.TestCase):
    def test_escala_acoes_em_milhares(self):
        emp = _emp({}, {"pl": 200e9, "pl_controladora": 200e9}, {"on": 5_000_000.0, "pn": 5_000_000.0,
                                                                  "tes_on": 0.0, "tes_pn": 0.0, "total": 10e6})
        mc, info = ind.valor_mercado(emp, 40.0, "PN", mcap_ref=402e9)
        self.assertEqual(info["escala_acoes"], 1000)
        self.assertAlmostEqual(mc, 400e9)
        mc2, info2 = ind.valor_mercado(emp, 40.0, "PN")  # sem referência: P/VP plausível escolhe a escala
        self.assertEqual(info2["escala_acoes"], 1000)

    def test_unit(self):
        emp = _emp({}, {"pl": 8e9}, {"on": 590e6, "pn": 443e6, "tes_on": 0.0, "tes_pn": 0.0, "total": 1033e6})
        mc, _ = ind.valor_mercado(emp, 40.0, "UNIT", acoes_por_unit=3)
        self.assertAlmostEqual(mc, 1033e6 * 40.0 / 3, delta=1e6)

    def test_diluicao_bonificacao(self):
        hist = {"2021": 100.0, "2022": 100.0, "2023": 140.0, "2024": 140.0, "2025": 141.0}
        taxa, sem = ind.diluicao(hist, emissoes={"2023": 0.0, "2025": 5.0})
        self.assertEqual(sem[0][0], "2023")
        self.assertLess(taxa, 0.01)


class Score(unittest.TestCase):
    def test_score_e_selo(self):
        anual = {str(a): _ano(a) for a in range(2020, 2026)}
        emp = _emp(anual, dict(anual["2025"]), {"on": 100.0, "pn": 0.0, "tes_on": 0.0, "tes_pn": 0.0, "total": 100.0})
        m = ind.calcular(emp, 0.6, 60.0, "Energia Elétrica")
        v = val.avaliar(m, emp)
        sc = scoring.pontuar(m, v)
        self.assertTrue(0 < sc["total_deterministico"] <= 70)
        self.assertEqual(set(sc["pilares"]), {"valuation", "crescimento", "rentabilidade", "saude"})
        al = [{"flag": "x", "severidade": "alta", "categoria": "armadilha"},
              {"flag": "y", "severidade": "media", "categoria": "armadilha"}]
        sc2 = dict(sc, pilares=dict(sc["pilares"], valuation=20.0))
        self.assertEqual(scoring.selo(sc2, al, m, v)["codigo"], "armadilha")
        self.assertEqual(scoring.selo(dict(sc2, pilares=dict(sc2["pilares"], rentabilidade=12, saude=12)), [], m, v)["codigo"],
                         "barata_solida")

    def test_formatacao(self):
        self.assertEqual(report.num(1234.5), "1.234,5")
        self.assertEqual(report.pct(0.153), "15,3%")
        self.assertEqual(report.rs_grande(2.5e9), "R$ 2,5 bi")
        self.assertEqual(report.pct(-0.00001), "0,0%")


def online():
    import analyze
    import macro
    mac = macro.snapshot()
    a = analyze.analisar("WEGE3", mac, noticias=False)
    assert a["indicadores"]["pl"] and a["score"]["total_deterministico"] > 0
    print(f"online OK: WEGE3 P/L {a['indicadores']['pl']:.1f} · score {a['score']['total_deterministico']}/70 · "
          f"{a['selo']['selo']}")


if __name__ == "__main__":
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    on = "--online" in sys.argv
    argv = [a for a in sys.argv if a != "--online"]
    r = unittest.main(argv=argv, exit=False, verbosity=1).result
    if on and r.wasSuccessful():
        online()
    sys.exit(0 if r.wasSuccessful() else 1)
