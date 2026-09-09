import glob
import os
import csv
import re
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)

CAMPOS = ["bloco", "ip", "hostname", "os", "protocolo", "porta", "estado", "servico", "versao"]


def carregar_dados():
    registros = []
    for arquivo in sorted(glob.glob("rela*.csv")):
        try:
            with open(arquivo, newline="", encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f, delimiter=";")
                for linha in reader:
                    linha = {k: (v.strip() if v else "") for k, v in linha.items()}
                    linha["_arquivo"] = os.path.basename(arquivo)
                    registros.append(linha)
        except Exception as e:
            print(f"Erro ao ler {arquivo}: {e}")
    return registros


DADOS = carregar_dados()

HTML = """<!DOCTYPE html>
<html lang="pt-br">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Relatorio de Portas</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #0f172a; color: #e2e8f0; }
.container { max-width: 1400px; margin: 0 auto; padding: 20px; }
h1 { text-align: center; margin-bottom: 5px; color: #38bdf8; font-size: 28px; }
p.sub { text-align: center; color: #94a3b8; margin-bottom: 20px; }
.stats { display: flex; flex-wrap: wrap; gap: 12px; justify-content: center; margin-bottom: 20px; }
.stat { background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 12px 20px; text-align: center; min-width: 120px; }
.stat .num { font-size: 24px; font-weight: bold; color: #38bdf8; }
.stat .lbl { font-size: 12px; color: #94a3b8; text-transform: uppercase; letter-spacing: 1px; }
.search-box { display: flex; gap: 10px; margin-bottom: 15px; flex-wrap: wrap; }
.search-box input[type=text] { flex: 1; min-width: 250px; padding: 12px 15px; border-radius: 8px; border: 1px solid #334155; background: #1e293b; color: #e2e8f0; font-size: 15px; }
.search-box input[type=text]:focus { outline: none; border-color: #38bdf8; }
.search-box button { padding: 12px 22px; border: none; border-radius: 8px; background: #0ea5e9; color: #fff; font-size: 15px; font-weight: bold; cursor: pointer; }
.search-box button:hover { background: #38bdf8; }
.selects { display: flex; gap: 10px; margin-bottom: 15px; flex-wrap: wrap; }
.selects select { padding: 10px; border-radius: 8px; border: 1px solid #334155; background: #1e293b; color: #e2e8f0; }
.meta { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 10px; }
.meta .info { color: #94a3b8; font-size: 14px; }
.meta .pager { display: flex; gap: 6px; align-items: center; }
.meta button { padding: 6px 12px; border: none; border-radius: 6px; background: #334155; color: #e2e8f0; cursor: pointer; }
.meta button:disabled { opacity: 0.4; cursor: not-allowed; }
table { width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.4); }
th { background: #0ea5e9; color: #fff; text-align: left; padding: 12px 14px; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; cursor: pointer; position: relative; user-select: none; }
th:hover { background: #38bdf8; }
th .arrow { font-size: 10px; margin-left: 5px; }
td { padding: 10px 14px; border-bottom: 1px solid #334155; font-size: 14px; word-break: break-all; }
tr:hover { background: #263449; }
.tag { display: inline-block; padding: 3px 10px; border-radius: 20px; font-size: 12px; font-weight: bold; }
.tag-open { background: #166534; color: #86efac; }
.tag-443 { background: #7c2d12; color: #fdba74; }
.empty { text-align: center; padding: 40px; color: #94a3b8; }
.note { text-align: center; color: #64748b; font-size: 12px; margin-top: 20px; }
</style>
</head>
<body>
<div class="container">
  <h1>&#128202; Relatorio de Portas</h1>
  <p class="sub">Escaneamento de servicos e portas abertas</p>

  <div class="stats">
    <div class="stat"><div class="num">{{ total }}</div><div class="lbl">Registros</div></div>
    <div class="stat"><div class="num">{{ ips }}</div><div class="lbl">IPs unicos</div></div>
    <div class="stat"><div class="num">{{ blocos }}</div><div class="lbl">Blocos</div></div>
    <div class="stat"><div class="num">{{ arquivos }}</div><div class="lbl">CSV lidos</div></div>
  </div>

  <div class="search-box">
    <input type="text" id="busca" placeholder="Pesquisar por IP, porta, servico, bloco, hostname, versao..." value="{{ q }}">
    <button onclick="carregar(1)">Buscar</button>
    <button onclick="limpar()">Limpar</button>
  </div>

  <div class="selects">
    <select id="filtro_bloco" onchange="carregar(1)">
      <option value="">Todos os blocos</option>
      {% for b in opcoes.bloco %}<option value="{{ b }}" {% if filtros.bloco == b %}selected{% endif %}>{{ b }}</option>{% endfor %}
    </select>
    <select id="filtro_servico" onchange="carregar(1)">
      <option value="">Todos os servicos</option>
      {% for s in opcoes.servico %}<option value="{{ s }}" {% if filtros.servico == s %}selected{% endif %}>{{ s }}</option>{% endfor %}
    </select>
    <select id="filtro_porta" onchange="carregar(1)">
      <option value="">Todas as portas</option>
      {% for p in opcoes.porta %}<option value="{{ p }}" {% if filtros.porta == p %}selected{% endif %}>{{ p }}</option>{% endfor %}
    </select>
    <select id="filtro_estado" onchange="carregar(1)">
      <option value="">Todos os estados</option>
      {% for e in opcoes.estado %}<option value="{{ e }}" {% if filtros.estado == e %}selected{% endif %}>{{ e }}</option>{% endfor %}
    </select>
  </div>

  <div class="meta">
    <div class="info" id="info">Exibindo {{ resultados|length }} de {{ qtd_total }} resultados</div>
    <div class="pager">
      <button id="ant" onclick="carregar({{ pagina - 1 }})">&#8592; Anterior</button>
      <span>Pagina <b id="pagina_atual">{{ pagina }}</b> de <b id="total_paginas">{{ total_paginas }}</b></span>
      <button id="prox" onclick="carregar({{ pagina + 1 }})">Proximo &#8594;</button>
    </div>
  </div>

  <div style="overflow-x:auto;">
  <table>
    <thead>
      <tr>
        <th onclick="ordenar('bloco')">Bloco <span class="arrow"></span></th>
        <th onclick="ordenar('ip')">IP <span class="arrow"></span></th>
        <th onclick="ordenar('hostname')">Hostname <span class="arrow"></span></th>
        <th onclick="ordenar('porta')">Porta <span class="arrow"></span></th>
        <th onclick="ordenar('servico')">Servico <span class="arrow"></span></th>
        <th onclick="ordenar('estado')">Estado <span class="arrow"></span></th>
        <th>Versao</th>
        <th onclick="ordenar('_arquivo')">Arquivo <span class="arrow"></span></th>
      </tr>
    </thead>
    <tbody id="corpo">
      {% for r in resultados %}
      <tr>
        <td>{{ r.bloco }}</td>
        <td><a href="#" style="color:#38bdf8" onclick="buscarFrase('{{ r.ip }}'); return false;">{{ r.ip }}</a></td>
        <td>{{ r.hostname }}</td>
        <td><span class="tag tag-443">{{ r.porta }}</span></td>
        <td>{{ r.servico }}</td>
        <td><span class="tag tag-open">{{ r.estado }}</span></td>
        <td>{{ r.versao }}</td>
        <td>{{ r._arquivo }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  </div>

  <div class="empty" id="vazio" style="display:none;">Nenhum resultado encontrado.</div>

  <p class="note">Total de arquivos processados: {{ arquivos }} ({{ arquivos_list }})</p>
</div>

<script>
let ordemCampo = "ip";
let ordemDir = 1;
let ignorarFiltro = false;

function preencherSelects() {
  if (ignorarFiltro) return;
  const form = new FormData();
  const busca = document.getElementById("busca").value;
  form.append("q", busca);
  fetch("/filtros", { method: "POST", body: form })
    .then(r => r.json())
    .then(d => {
      atualizarSelect("filtro_bloco", d.bloco, "Todos os blocos");
      atualizarSelect("filtro_servico", d.servico, "Todos os servicos");
      atualizarSelect("filtro_porta", d.porta, "Todas as portas");
      atualizarSelect("filtro_estado", d.estado, "Todos os estados");
    });
}

function atualizarSelect(id, lista, placeholder) {
  const sel = document.getElementById(id);
  const atual = sel.value;
  let html = "<option value=''>" + placeholder + "</option>";
  lista.forEach(i => { html += "<option value='" + i + "'>" + i + "</option>"; });
  sel.innerHTML = html;
  sel.value = atual;
}

function carregar(pag) {
  const form = new FormData();
  form.append("q", document.getElementById("busca").value);
  form.append("pagina", pag);
  form.append("bloco", document.getElementById("filtro_bloco").value);
  form.append("servico", document.getElementById("filtro_servico").value);
  form.append("porta", document.getElementById("filtro_porta").value);
  form.append("estado", document.getElementById("filtro_estado").value);
  form.append("ordemcampo", ordemCampo);
  form.append("ordemdir", ordemDir);
  fetch("/buscar", { method: "POST", body: form })
    .then(r => r.json())
    .then(d => {
      document.getElementById("corpo").innerHTML = d.tabela;
      document.getElementById("info").textContent = d.info;
      document.getElementById("pagina_atual").textContent = d.pagina;
      document.getElementById("total_paginas").textContent = d.total_paginas;
      document.getElementById("ant").disabled = d.pagina <= 1;
      document.getElementById("prox").disabled = d.pagina >= d.total_paginas;
      document.getElementById("vazio").style.display = d.resultados === 0 ? "block" : "none";
      preencherSelects();
    });
}

function ordenar(campo) {
  if (ordemCampo === campo) ordemDir = -ordemDir;
  else { ordemCampo = campo; ordemDir = 1; }
  carregar(1);
}

function limpar() {
  document.getElementById("busca").value = "";
  ignorarFiltro = true;
  document.getElementById("filtro_bloco").value = "";
  document.getElementById("filtro_servico").value = "";
  document.getElementById("filtro_porta").value = "";
  document.getElementById("filtro_estado").value = "";
  ignorarFiltro = false;
  carregar(1);
}

function buscarFrase(frase) {
  document.getElementById("busca").value = frase;
  carregar(1);
}

document.getElementById("busca").addEventListener("keydown", function(e) {
  if (e.key === "Enter") carregar(1);
});

carregar(1);
</script>
</body>
</html>
"""


@app.route("/")
def index():
    filtros = {c: request.args.get(c, "") for c in ["bloco", "servico", "porta", "estado"]}
    q = request.args.get("q", "")
    filtrados = filtrar(DADOS, q, filtros)

    opcoes = {
        "bloco": sorted({r["bloco"] for r in DADOS if r["bloco"]}),
        "servico": sorted({r["servico"] for r in DADOS if r["servico"]}),
        "porta": sorted({r["porta"] for r in DADOS if r["porta"]}, key=lambda x: int(x) if x.isdigit() else 999999),
        "estado": sorted({r["estado"] for r in DADOS if r["estado"]}),
    }

    pagina, total_paginas, resultados = paginar(filtrados, request.args.get("pagina", 1))

    arquivos_list = sorted({r["_arquivo"] for r in DADOS})

    return render_template_string(
        HTML,
        total=len(DADOS),
        ips=len({r["ip"] for r in DADOS if r["ip"]}),
        blocos=len({r["bloco"] for r in DADOS if r["bloco"]}),
        arquivos=len(arquivos_list),
        arquivos_list=", ".join(arquivos_list),
        opcoes=opcoes,
        filtros=filtros,
        q=q,
        resultados=resultados,
        pagina=pagina,
        total_paginas=total_paginas,
        qtd_total=len(filtrados),
    )


@app.route("/buscar", methods=["POST"])
def buscar():
    q = request.form.get("q", "")
    filtros = {c: request.form.get(c, "") for c in ["bloco", "servico", "porta", "estado"]}
    ordemcampo = request.form.get("ordemcampo", "ip")
    ordemdir = int(request.form.get("ordemdir", 1))

    filtrados = filtrar(DADOS, q, filtros)
    filtrados = ordenar(filtrados, ordemcampo, ordemdir)

    pagina, total_paginas, resultados = paginar(filtrados, request.form.get("pagina", 1))

    tabela = ""
    for r in resultados:
        tabela += f"""<tr>
<td>{r['bloco']}</td>
<td><a href="#" style="color:#38bdf8" onclick="buscarFrase('{r['ip']}'); return false;">{r['ip']}</a></td>
<td>{r['hostname']}</td>
<td><span class="tag tag-443">{r['porta']}</span></td>
<td>{r['servico']}</td>
<td><span class="tag tag-open">{r['estado']}</span></td>
<td>{r['versao']}</td>
<td>{r['_arquivo']}</td>
</tr>"""

    return jsonify({
        "tabela": tabela,
        "info": f"Exibindo {len(resultados)} de {len(filtrados)} resultados",
        "pagina": pagina,
        "total_paginas": total_paginas,
        "resultados": len(resultados),
    })


@app.route("/filtros", methods=["POST"])
def filtros():
    q = request.form.get("q", "")
    filtrados = filtrar(DADOS, q, {})
    return jsonify({
        "bloco": sorted({r["bloco"] for r in filtrados if r["bloco"]}),
        "servico": sorted({r["servico"] for r in filtrados if r["servico"]}),
        "porta": sorted({r["porta"] for r in filtrados if r["porta"]}, key=lambda x: int(x) if x.isdigit() else 999999),
        "estado": sorted({r["estado"] for r in filtrados if r["estado"]}),
    })


def filtrar(dados, q, filtros):
    q = q.lower().strip()
    resultado = []
    for r in dados:
        if filtros.get("bloco") and r["bloco"] != filtros["bloco"]:
            continue
        if filtros.get("servico") and r["servico"] != filtros["servico"]:
            continue
        if filtros.get("porta") and r["porta"] != filtros["porta"]:
            continue
        if filtros.get("estado") and r["estado"] != filtros["estado"]:
            continue
        if q:
            if not any(q in str(r[c]).lower() for c in CAMPOS):
                continue
        resultado.append(r)
    return resultado


def ordenar(dados, campo, direcao):
    def chave(r):
        v = r.get(campo, "")
        return (int(v) if v.isdigit() else v.lower(), v)
    return sorted(dados, key=chave, reverse=(direcao < 0))


def paginar(dados, pagina):
    try:
        pagina = int(pagina)
    except (ValueError, TypeError):
        pagina = 1
    tamanho = 50
    total_paginas = max(1, -(-len(dados) // tamanho))
    pagina = max(1, min(pagina, total_paginas))
    inicio = (pagina - 1) * tamanho
    return pagina, total_paginas, dados[inicio:inicio + tamanho]


if __name__ == "__main__":
    if not DADOS:
        print("Nenhum arquivo rela*.csv encontrado no diretorio atual.")
    print(f"Carregados {len(DADOS)} registros de ({', '.join(sorted({r['_arquivo'] for r in DADOS}))})")
    app.run(debug=True, host="0.0.0.0", port=5000)
