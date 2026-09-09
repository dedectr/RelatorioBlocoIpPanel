import glob
import os
import csv
import re
import io
import time
from flask import Flask, request, jsonify, render_template_string, Response

app = Flask(__name__)

CAMPOS = ["bloco", "ip", "hostname", "os", "protocolo", "porta", "estado", "servico", "versao"]
COLUNAS_EXPORT = ["bloco", "ip", "hostname", "os", "protocolo", "porta", "estado", "servico", "versao"]

STATUS_DATA = {
    "arquivos_encontrados": [],
    "arquivos_erros": [],
    "total_registros": 0,
    "timestamp": None,
    "carregado": False,
}

IP_RE = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$")


def normaliza_ip(v):
    v = (v or "").strip()
    if IP_RE.match(v):
        return v
    return v


def carregar_dados():
    registros = []
    arquivos_ok = []
    arquivos_erro = []
    arquivos_csv = sorted(glob.glob("rela*.csv"))

    if not arquivos_csv:
        arquivos_erro.append({"arquivo": "(nenhum rela*.csv encontrado)", "erro": "Nenhum arquivo CSV no diretorio atual"})

    for arquivo in arquivos_csv:
        try:
            with open(arquivo, newline="", encoding="utf-8", errors="replace") as f:
                conteudo = f.read()
                if not conteudo.strip():
                    arquivos_erro.append({"arquivo": os.path.basename(arquivo), "erro": "Arquivo vazio"})
                    continue
                f.seek(0)
                reader = csv.DictReader(f, delimiter=";")
                count = 0
                for linha in reader:
                    linha = {k: (v.strip() if v else "") for k, v in linha.items()}
                    if not linha.get("ip"):
                        continue
                    linha["_arquivo"] = os.path.basename(arquivo)
                    registros.append(linha)
                    count += 1
                arquivos_ok.append({"arquivo": os.path.basename(arquivo), "registros": count})
        except Exception as e:
            arquivos_erro.append({"arquivo": os.path.basename(arquivo), "erro": str(e)})

    STATUS_DATA["arquivos_encontrados"] = arquivos_ok
    STATUS_DATA["arquivos_erros"] = arquivos_erro
    STATUS_DATA["total_registros"] = len(registros)
    STATUS_DATA["timestamp"] = time.strftime("%d/%m/%Y %H:%M:%S")
    STATUS_DATA["carregado"] = True

    return registros


DADOS = carregar_dados()


def agrupar_por_ip(registros):
    """Agrupa registros por IP. Retorna lista de dicts com servicos/portas agregados."""
    ips = {}
    for r in registros:
        ip = r.get("ip", "")
        if not ip:
            continue
        g = ips.setdefault(ip, {
            "ip": ip,
            "hostname": r.get("hostname", ""),
            "bloco": r.get("bloco", ""),
            "_arquivo": r.get("_arquivo", ""),
            "qtd_portas": 0,
            "portas": [],
        })
        if r.get("hostname") and not g["hostname"]:
            g["hostname"] = r["hostname"]
        if not g["bloco"]:
            g["bloco"] = r.get("bloco", "")
        porta = r.get("porta", "").strip()
        if porta:
            g["portas"].append({
                "porta": porta,
                "servico": r.get("servico", ""),
                "estado": r.get("estado", ""),
                "versao": r.get("versao", ""),
                "protocolo": r.get("protocolo", ""),
                "os": r.get("os", ""),
            })
            g["qtd_portas"] += 1
    return list(ips.values())


def lista_para_ip(ip, dados=None):
    """Agrupado por IP para linhas da tabela."""
    dados = dados if dados is not None else DADOS
    grupos = agrupar_por_ip([r for r in dados if r.get("ip") == ip])
    if not grupos:
        return None
    return grupos[0]

HTML = """<!DOCTYPE html>
<html lang="pt-br">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Relatorio de Portas</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
:root {
  --bg: #0f172a; --panel: #1e293b; --border: #334155; --text: #e2e8f0;
  --muted: #94a3b8; --accent: #38bdf8; --accent2: #0ea5e9; --hover: #263449;
  --shadow: rgba(0,0,0,0.4); --input: #1e293b;
}
html[data-theme="light"] {
  --bg: #f1f5f9; --panel: #ffffff; --border: #cbd5e1; --text: #1e293b;
  --muted: #64748b; --accent: #0284c7; --accent2: #0369a1; --hover: #f8fafc;
  --shadow: rgba(0,0,0,0.1); --input: #ffffff;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: var(--bg); color: var(--text); transition: background .3s, color .3s; }
.container { max-width: 1400px; margin: 0 auto; padding: 20px; }
h1 { text-align: center; margin-bottom: 5px; color: var(--accent); font-size: 28px; }
p.sub { text-align: center; color: var(--muted); margin-bottom: 20px; }
.topbar { display: flex; justify-content: flex-end; margin-bottom: 15px; }
.icon-btn { background: var(--panel); border: 1px solid var(--border); color: var(--text); padding: 8px 14px; border-radius: 8px; cursor: pointer; font-size: 14px; }
.icon-btn:hover { border-color: var(--accent); color: var(--accent); }

.stats { display: flex; flex-wrap: wrap; gap: 12px; justify-content: center; margin-bottom: 20px; }
.stat { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 12px 20px; text-align: center; min-width: 120px; }
.stat .num { font-size: 24px; font-weight: bold; color: var(--accent); }
.stat .lbl { font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; }

.dashboard { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; margin-bottom: 25px; }
.chart-card { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 16px; }
.chart-card h3 { color: var(--accent); font-size: 14px; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 1px; }
.chart-box { position: relative; height: 220px; }

.search-box { display: flex; gap: 10px; margin-bottom: 15px; flex-wrap: wrap; }
.search-box input[type=text] { flex: 1; min-width: 250px; padding: 12px 15px; border-radius: 8px; border: 1px solid var(--border); background: var(--input); color: var(--text); font-size: 15px; }
.search-box input[type=text]:focus { outline: none; border-color: var(--accent); }
.search-box button { padding: 12px 22px; border: none; border-radius: 8px; background: var(--accent2); color: #fff; font-size: 15px; font-weight: bold; cursor: pointer; }
.search-box button:hover { background: var(--accent); }
.search-box .ghost { background: var(--panel); color: var(--text); border: 1px solid var(--border); }
.selects { display: flex; gap: 10px; margin-bottom: 15px; flex-wrap: wrap; }
.selects select { padding: 10px; border-radius: 8px; border: 1px solid var(--border); background: var(--input); color: var(--text); }
.meta { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 10px; }
.meta .info { color: var(--muted); font-size: 14px; }
.meta .pager { display: flex; gap: 6px; align-items: center; }
.meta button { padding: 6px 12px; border: none; border-radius: 6px; background: var(--panel); color: var(--text); cursor: pointer; }
.meta button:disabled { opacity: 0.4; cursor: not-allowed; }
table { width: 100%; border-collapse: collapse; background: var(--panel); border-radius: 10px; overflow: hidden; box-shadow: 0 4px 20px var(--shadow); }
th { background: var(--accent2); color: #fff; text-align: left; padding: 12px 14px; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; cursor: pointer; position: relative; user-select: none; }
th:hover { background: var(--accent); }
th .arrow { font-size: 10px; margin-left: 5px; }
td { padding: 10px 14px; border-bottom: 1px solid var(--border); font-size: 14px; word-break: break-all; }
tr:hover { background: var(--hover); }
tr.selected { background: rgba(56,189,248,0.12); }
.tag { display: inline-block; padding: 3px 10px; border-radius: 20px; font-size: 12px; font-weight: bold; }
.tag-open { background: #166534; color: #86efac; }
.tag-closed { background: #7f1d1d; color: #fca5a5; }
.tag-filtered { background: #78350f; color: #fcd34d; }
.tag-port { background: #7c2d12; color: #fdba74; }
.empty { text-align: center; padding: 40px; color: var(--muted); }
.note { text-align: center; color: var(--muted); font-size: 12px; margin-top: 20px; }
.mini-ports { display: inline-flex; flex-wrap: wrap; gap: 4px; }
.mini-port { background: var(--panel); border: 1px solid var(--border); color: var(--accent); padding: 1px 7px; border-radius: 12px; font-size: 11px; }
.status-banner { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 15px 20px; margin-bottom: 20px; }
.status-banner h3 { color: var(--accent); font-size: 14px; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 1px; }
.status-banner .status-ok { color: #86efac; }
.status-banner .status-erro { color: #fca5a5; }
.status-banner li { padding: 4px 0; font-size: 13px; color: var(--text); }
.status-banner li .icon { margin-right: 6px; }
.status-banner .toggle-btn { background: none; border: 1px solid var(--border); color: var(--muted); padding: 4px 12px; border-radius: 6px; cursor: pointer; font-size: 12px; margin-top: 8px; }
.status-banner .toggle-btn:hover { border-color: var(--accent); color: var(--accent); }
.status-details { display: none; margin-top: 10px; }
.no-data-banner { background: var(--panel); border: 2px solid #dc2626; border-radius: 10px; padding: 30px; text-align: center; margin-bottom: 20px; }
.no-data-banner h2 { color: #fca5a5; margin-bottom: 10px; }
.no-data-banner p { color: var(--muted); }

.modal-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 1000; justify-content: center; align-items: center; padding: 20px; }
.modal-overlay.active { display: flex; }
.modal { background: var(--panel); border: 1px solid var(--border); border-radius: 16px; width: 100%; max-width: 800px; max-height: 85vh; overflow-y: auto; box-shadow: 0 20px 60px rgba(0,0,0,0.6); }
.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 20px 25px; border-bottom: 1px solid var(--border); background: var(--bg); border-radius: 16px 16px 0 0; }
.modal-header h2 { color: var(--accent); font-size: 20px; }
.modal-close { background: none; border: none; color: var(--muted); font-size: 28px; cursor: pointer; padding: 0 8px; }
.modal-close:hover { color: #f87171; }
.modal-body { padding: 25px; }
.ip-hero { text-align: center; margin-bottom: 25px; padding: 20px; background: var(--bg); border-radius: 12px; border: 1px solid var(--border); }
.ip-hero .ip-addr { font-size: 32px; font-weight: bold; color: var(--accent); margin-bottom: 5px; word-break: break-all; }
.ip-hero .ip-hostname { font-size: 14px; color: var(--muted); }
.ip-hero .ip-bloco { display: inline-block; margin-top: 8px; background: var(--panel); border: 1px solid var(--border); padding: 4px 12px; border-radius: 20px; font-size: 12px; color: var(--text); }
.info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 20px; }
.info-card { background: var(--bg); border: 1px solid var(--border); border-radius: 10px; padding: 14px; }
.info-card .label { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px; }
.info-card .value { font-size: 15px; font-weight: bold; color: var(--text); word-break: break-all; }
.ports-section h3 { color: var(--accent); font-size: 15px; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 1px; }
.port-card { background: var(--bg); border: 1px solid var(--border); border-radius: 10px; padding: 14px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; }
.port-card .port-num { font-size: 20px; font-weight: bold; color: #fdba74; }
.port-card .port-info { flex: 1; min-width: 200px; }
.port-card .port-svc { font-size: 14px; color: var(--text); }
.port-card .port-ver { font-size: 12px; color: var(--muted); }
.port-card .port-state { text-align: right; }
.loading-spinner { text-align: center; padding: 40px; color: var(--muted); }
.loading-spinner::after { content: ''; display: inline-block; width: 30px; height: 30px; border: 3px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.8s linear infinite; margin-top: 10px; }
@keyframes spin { to { transform: rotate(360deg); } }
.bars-container { display: flex; flex-direction: column; gap: 8px; }
.bar-row { display: flex; align-items: center; gap: 10px; }
.bar-label { width: 110px; font-size: 12px; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.bar-track { flex: 1; height: 14px; background: var(--bg); border: 1px solid var(--border); border-radius: 7px; overflow: hidden; }
.bar-fill { height: 100%; background: var(--accent); border-radius: 7px; transition: width .4s; }
.bar-count { width: 40px; font-size: 12px; color: var(--muted); text-align: right; }
@media (max-width: 640px) {
  .info-grid { grid-template-columns: 1fr; }
  .container { padding: 12px; }
  .search-box input[type=text] { min-width: 100%; }
  .selects select { flex: 1 1 100%; }
  table { font-size: 12px; }
  th, td { padding: 8px 8px; }
  .ip-hero .ip-addr { font-size: 24px; }
}
</style>
</head>
<body>
<div class="container">
  <div class="topbar">
    <button class="icon-btn" onclick="alternarTema()" id="btnTema">&#127769; Tema</button>
  </div>

  <h1>&#128202; Relatorio de Portas</h1>
  <p class="sub">Escaneamento de servicos e portas abertas</p>

  {% if not dados_disponiveis %}
  <div class="no-data-banner">
    <h2>Nenhum dado disponivel</h2>
    <p>Nenhum arquivo <b>rela*.csv</b> foi encontrado ou os arquivos estao vazios.</p>
    <p style="margin-top:8px; color:var(--muted);">Coloque seus arquivos CSV no mesmo diretorio do script e reinicie.</p>
  </div>
  {% endif %}

  <div class="status-banner">
    <h3>Status dos Dados</h3>
    <div>
      {% for arq in status.arquivos_encontrados %}
        <li><span class="icon status-ok">&#10003;</span> <b>{{ arq.arquivo }}</b> &mdash; {{ arq.registros }} registros</li>
      {% endfor %}
      {% for arq in status.arquivos_erros %}
        <li><span class="icon status-erro">&#10007;</span> <b>{{ arq.arquivo }}</b> &mdash; {{ arq.erro }}</li>
      {% endfor %}
    </div>
    <li style="margin-top:6px;"><span class="icon status-ok">&#9679;</span> Total: <b>{{ total }}</b> registros validos</li>
    <li><span class="icon" style="color:var(--muted);">&#9679;</span> Carregado em: {{ status.timestamp }}</li>
    <button class="toggle-btn" onclick="toggleStatus()">Mostrar detalhes</button>
    <div class="status-details" id="statusDetails">
      <ul>
        {% for arq in status.arquivos_encontrados %}
        <li>&bull; {{ arq.arquivo }}: {{ arq.registros }} linhas OK</li>
        {% endfor %}
        {% for arq in status.arquivos_erros %}
        <li style="color:#fca5a5;">&bull; {{ arq.arquivo }}: {{ arq.erro }}</li>
        {% endfor %}
      </ul>
    </div>
  </div>

  <div class="stats">
    <div class="stat"><div class="num">{{ total }}</div><div class="lbl">Registros</div></div>
    <div class="stat"><div class="num">{{ ips }}</div><div class="lbl">IPs unicos</div></div>
    <div class="stat"><div class="num">{{ blocos }}</div><div class="lbl">Blocos</div></div>
    <div class="stat"><div class="num">{{ arquivos }}</div><div class="lbl">CSV lidos</div></div>
  </div>

  <div class="dashboard">
    <div class="chart-card"><h3>Portas mais comuns</h3><div class="chart-box"><canvas id="grafPortas"></canvas></div></div>
    <div class="chart-card"><h3>Servicos mais comuns</h3><div class="chart-box"><canvas id="grafServicos"></canvas></div></div>
    <div class="chart-card"><h3>Distribuicao por bloco</h3><div class="chart-box"><canvas id="grafBlocos"></canvas></div></div>
    <div class="chart-card"><h3>Estados dos servicos</h3><div class="chart-box"><canvas id="grafEstados"></canvas></div></div>
  </div>

  <div class="search-box">
    <input type="text" id="busca" placeholder="Pesquisar por IP, porta, servico, bloco, hostname, versao..." value="{{ q }}">
    <button onclick="carregar(1)">Buscar</button>
    <button class="ghost" onclick="limpar()">Limpar</button>
    <button class="ghost" onclick="exportar('csv')">Exportar CSV</button>
    <button class="ghost" onclick="exportar('json')">Exportar JSON</button>
    <button class="ghost" onclick="copiarSelecionados()" id="btnCopiar" disabled>Copiar IPs (0)</button>
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
    <label style="font-size:13px; color:var(--muted);"><input type="checkbox" id="selTodos" onchange="selecionarTodos()"> Selecionar todos</label>
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
        <th style="cursor:default; width:30px;"></th>
        <th onclick="ordenar('bloco')">Bloco <span class="arrow"></span></th>
        <th onclick="ordenar('ip')">IP <span class="arrow"></span></th>
        <th onclick="ordenar('hostname')">Hostname <span class="arrow"></span></th>
        <th style="cursor:default;">Portas</th>
        <th style="cursor:default;">Estado</th>
        <th onclick="ordenar('_arquivo')">Arquivo <span class="arrow"></span></th>
      </tr>
    </thead>
    <tbody id="corpo">
      {% for r in resultados %}
      <tr data-ip="{{ r.ip }}">
        <td><input type="checkbox" class="sel-linha" value="{{ r.ip }}" onchange="atualizarSelecao()"></td>
        <td>{{ r.bloco }}</td>
        <td><a href="#" style="color:var(--accent); cursor:pointer; text-decoration:underline" onclick="abrirDetalheIP('{{ r.ip }}'); return false;">{{ r.ip }}</a></td>
        <td>{{ r.hostname }}</td>
        <td>
          <div class="mini-ports">
            {% for p in r.portas %}
            <span class="mini-port" data-estado="{{ p.estado }}" title="{{ p.servico }} ({{ p.estado }})">{{ p.porta }}</span>
            {% endfor %}
          </div>
        </td>
        <td>
          {% set estados = r.portas|map(attribute='estado')|list %}
          <span class="tag tag-open">{{ r.qtd_portas }} porta(s)</span>
        </td>
        <td>{{ r._arquivo }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  </div>

  <div class="empty" id="vazio" style="display:none;">Nenhum resultado encontrado.</div>

  <p class="note">Total de arquivos processados: {{ arquivos }} ({{ arquivos_list }})</p>
</div>

<div class="modal-overlay" id="modalOverlay" onclick="fecharModal(event)">
  <div class="modal" onclick="event.stopPropagation()">
    <div class="modal-header">
      <h2>Detalhes do IP</h2>
      <button class="modal-close" onclick="fecharModalDireto()">&times;</button>
    </div>
    <div class="modal-body" id="modalBody">
      <div class="loading-spinner">Carregando detalhes...</div>
    </div>
  </div>
</div>

<script>
let ordemCampo = "ip";
let ordemDir = 1;
let ignorarFiltro = false;
let graficos = {};
let selected = new Set();

function readTheme() { return document.documentElement.getAttribute('data-theme') || 'dark'; }

function alternarTema() {
  const atual = readTheme();
  document.documentElement.setAttribute('data-theme', atual === 'dark' ? 'light' : 'dark');
  localStorage.setItem('tema', atual === 'dark' ? 'light' : 'dark');
  graficos.forEach(g => {
    if (g) g.options.scales.x.ticks.color = getComputedStyle(document.body).color;
    if (g) g.options.scales.y.ticks.color = getComputedStyle(document.body).color;
  });
}

document.documentElement.setAttribute('data-theme', localStorage.getItem('tema') || 'dark');

function preencherSelects() {
  if (ignorarFiltro) return;
  const form = new FormData();
  form.append("q", document.getElementById("busca").value);
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

function obterFiltros() {
  return {
    q: document.getElementById("busca").value,
    bloco: document.getElementById("filtro_bloco").value,
    servico: document.getElementById("filtro_servico").value,
    porta: document.getElementById("filtro_porta").value,
    estado: document.getElementById("filtro_estado").value,
  };
}

function carregar(pag) {
  const f = obterFiltros();
  const form = new FormData();
  form.append("q", f.q);
  form.append("pagina", pag);
  form.append("bloco", f.bloco);
  form.append("servico", f.servico);
  form.append("porta", f.porta);
  form.append("estado", f.estado);
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
      document.getElementById("selTodos").checked = false;
      selected.clear();
      atualizarSelecao();
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

function toggleStatus() {
  const el = document.getElementById("statusDetails");
  el.style.display = el.style.display === "block" ? "none" : "block";
}

function abrirDetalheIP(ip) {
  const overlay = document.getElementById("modalOverlay");
  const body = document.getElementById("modalBody");
  overlay.classList.add("active");
  body.innerHTML = '<div class="loading-spinner">Carregando detalhes...</div>';

  fetch("/ip/" + encodeURIComponent(ip))
    .then(r => r.json())
    .then(d => {
      if (d.erro) {
        body.innerHTML = '<p style="color:#fca5a5; text-align:center;">' + d.erro + '</p>';
        return;
      }
      let html = '';
      html += '<div class="ip-hero">';
      html += '  <div class="ip-addr">' + d.ip + '</div>';
      html += '  <div class="ip-hostname">' + (d.hostname || 'Sem hostname') + '</div>';
      html += '  <div class="ip-bloco">Bloco: ' + (d.bloco || 'N/A') + '</div>';
      html += '</div>';

      html += '<div class="info-grid">';
      html += '  <div class="info-card"><div class="label">IP</div><div class="value">' + d.ip + '</div></div>';
      html += '  <div class="info-card"><div class="label">Hostname</div><div class="value">' + (d.hostname || '-') + '</div></div>';
      html += '  <div class="info-card"><div class="label">Bloco / Rede</div><div class="value">' + (d.bloco || '-') + '</div></div>';
      html += '  <div class="info-card"><div class="label">Arquivo Origem</div><div class="value">' + (d._arquivo || '-') + '</div></div>';
      html += '  <div class="info-card"><div class="label">Total de portas</div><div class="value">' + d.estatisticas.total + '</div></div>';
      html += '  <div class="info-card"><div class="label">Abertas / Fechadas</div><div class="value">' + d.estatisticas.open + ' / ' + d.estatisticas.closed + '</div></div>';
      html += '</div>';

      if (d.portas && d.portas.length > 0) {
        html += '<div class="ports-section"><h3>Portas (' + d.portas.length + ')</h3>';
        d.portas.forEach(p => {
          let stateClass = 'tag-open';
          if (p.estado && p.estado.toLowerCase() === 'closed') stateClass = 'tag-closed';
          else if (p.estado && p.estado.toLowerCase() === 'filtered') stateClass = 'tag-filtered';
          html += '<div class="port-card">';
          html += '  <div class="port-num">' + p.porta + '</div>';
          html += '  <div class="port-info">';
          html += '    <div class="port-svc">' + (p.servico || 'Desconhecido') + '</div>';
          html += '    <div class="port-ver">' + (p.versao || 'N/A') + ' &mdash; OS: ' + (p.os || 'N/A') + ' &mdash; Proto: ' + (p.protocolo || 'N/A') + '</div>';
          html += '  </div>';
          html += '  <div class="port-state"><span class="tag ' + stateClass + '">' + (p.estado || '?') + '</span></div>';
          html += '</div>';
        });
        html += '</div>';
      } else {
        html += '<p style="text-align:center; color:var(--muted); padding:20px;">Nenhuma porta registrada para este IP.</p>';
      }

      body.innerHTML = html;
    })
    .catch(() => {
      body.innerHTML = '<p style="color:#fca5a5; text-align:center;">Erro ao buscar detalhes do IP.</p>';
    });
}

function fecharModal(e) {
  if (e.target === document.getElementById("modalOverlay")) {
    document.getElementById("modalOverlay").classList.remove("active");
  }
}

function fecharModalDireto() {
  document.getElementById("modalOverlay").classList.remove("active");
}

function selecionarTodos() {
  const on = document.getElementById("selTodos").checked;
  document.querySelectorAll(".sel-linha").forEach(cb => {
    cb.checked = on;
    if (on) selected.add(cb.value); else selected.delete(cb.value);
  });
  atualizarSelecao();
}

function atualizarSelecao() {
  document.querySelectorAll(".sel-linha:checked").forEach(cb => selected.add(cb.value));
  document.querySelectorAll(".sel-linha:not(:checked)").forEach(cb => selected.delete(cb.value));
  const btn = document.getElementById("btnCopiar");
  btn.disabled = selected.size === 0;
  btn.textContent = "Copiar IPs (" + selected.size + ")";
  document.querySelectorAll("tr").forEach(tr => {
    const ip = tr.getAttribute("data-ip");
    tr.classList.toggle("selected", ip && selected.has(ip));
  });
}

function copiarSelecionados() {
  const lista = Array.from(selected).sort().join("\n");
  navigator.clipboard.writeText(lista).then(() => {
    const btn = document.getElementById("btnCopiar");
    const velho = btn.textContent;
    btn.textContent = "Copiado!";
    setTimeout(() => btn.textContent = velho, 1500);
  });
}

function exportar(formato) {
  const f = obterFiltros();
  const params = new URLSearchParams({
    formato: formato,
    q: f.q,
    bloco: f.bloco,
    servico: f.servico,
    porta: f.porta,
    estado: f.estado,
  });
  window.location.href = "/exportar?" + params.toString();
}

function carregarGraficos() {
  fetch("/estatisticas")
    .then(r => r.json())
    .then(d => {
      const texto = getComputedStyle(document.body).color;
      const acento = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim();

      if (graficos.grafPortas) graficos.grafPortas.destroy();
      graficos.grafPortas = new Chart(document.getElementById("grafPortas"), {
        type: 'bar',
        data: { labels: d.portas.map(x => x.nome), datasets: [{ label: 'Portas', data: d.portas.map(x => x.total), backgroundColor: acento || '#38bdf8' }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { ticks: { color: texto } }, y: { ticks: { color: texto }, beginAtZero: true } } }
      });

      if (graficos.grafServicos) graficos.grafServicos.destroy();
      graficos.grafServicos = new Chart(document.getElementById("grafServicos"), {
        type: 'bar',
        data: { labels: d.servicos.map(x => x.nome), datasets: [{ label: 'Servicos', data: d.servicos.map(x => x.total), backgroundColor: '#f59e0b' }] },
        options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { ticks: { color: texto }, beginAtZero: true }, y: { ticks: { color: texto } } } }
      });

      if (graficos.grafBlocos) graficos.grafBlocos.destroy();
      graficos.grafBlocos = new Chart(document.getElementById("grafBlocos"), {
        type: 'bar',
        data: { labels: d.blocos.map(x => x.nome), datasets: [{ label: 'Blocos', data: d.blocos.map(x => x.total), backgroundColor: '#a855f7' }] },
        options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { ticks: { color: texto }, beginAtZero: true }, y: { ticks: { color: texto } } } }
      });

      if (graficos.grafEstados) graficos.grafEstados.destroy();
      const cores = { open: '#22c55e', closed: '#ef4444', filtered: '#eab308' };
      graficos.grafEstados = new Chart(document.getElementById("grafEstados"), {
        type: 'doughnut',
        data: { labels: d.estados.map(x => x.nome), datasets: [{ data: d.estados.map(x => x.total), backgroundColor: d.estados.map(x => cores[x.nome.toLowerCase()] || '#94a3b8') }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { labels: { color: texto } } } }
      });
    });
}

document.addEventListener("keydown", function(e) {
  if (e.key === "Escape") fecharModalDireto();
});

document.getElementById("busca").addEventListener("keydown", function(e) {
  if (e.key === "Enter") carregar(1);
});

carregar(1);
carregarGraficos();
</script>
</body>
</html>
"""


@app.route("/")
def index():
    filtros = {c: request.args.get(c, "") for c in ["bloco", "servico", "porta", "estado"]}
    q = request.args.get("q", "")
    filtrados = filtrar(DADOS, q, filtros)
    agrupados = agrupar_por_ip(filtrados)

    opcoes = {
        "bloco": sorted({r["bloco"] for r in DADOS if r["bloco"]}),
        "servico": sorted({r["servico"] for r in DADOS if r["servico"]}),
        "porta": sorted({r["porta"].strip() for r in DADOS if r["porta"]}, key=lambda x: int(x) if x.isdigit() else 999999),
        "estado": sorted({r["estado"] for r in DADOS if r["estado"]}),
    }

    pagina, total_paginas, resultados = paginar(agrupados, request.args.get("pagina", 1))

    arquivos_list = sorted({r["_arquivo"] for r in DADOS})

    return render_template_string(
        HTML,
        total=len(DADOS),
        ips=len(agrupados),
        blocos=len({r["bloco"] for r in DADOS if r["bloco"]}),
        arquivos=len(arquivos_list),
        arquivos_list=", ".join(arquivos_list),
        opcoes=opcoes,
        filtros=filtros,
        q=q,
        resultados=resultados,
        pagina=pagina,
        total_paginas=total_paginas,
        qtd_total=len(agrupados),
        status=STATUS_DATA,
        dados_disponiveis=len(DADOS) > 0,
    )


@app.route("/buscar", methods=["POST"])
def buscar():
    q = request.form.get("q", "")
    filtros = {c: request.form.get(c, "") for c in ["bloco", "servico", "porta", "estado"]}
    ordemcampo = request.form.get("ordemcampo", "ip")
    ordemdir = int(request.form.get("ordemdir", 1))

    filtrados = filtrar(DADOS, q, filtros)
    agrupados = agrupar_por_ip(filtrados)
    agrupados = ordenar(agrupados, ordemcampo, ordemdir)

    pagina, total_paginas, resultados = paginar(agrupados, request.form.get("pagina", 1))

    def esc(v):
        return (v or "").replace("'", "&#39;").replace('"', "&quot;")

    tabela = ""
    for r in resultados:
        mini = ""
        for p in r["portas"]:
            mini += f'<span class="mini-port" title="{esc(p["servico"])} ({esc(p["estado"])})">{esc(p["porta"])}</span>'
        if not mini:
            mini = '<span style="color:var(--muted);font-size:12px;">sem porta</span>'
        tabela += f"""<tr data-ip="{esc(r['ip'])}">
<td><input type="checkbox" class="sel-linha" value="{esc(r['ip'])}" onchange="atualizarSelecao()"></td>
<td>{esc(r['bloco'])}</td>
<td><a href="#" style="color:var(--accent); cursor:pointer; text-decoration:underline" onclick="abrirDetalheIP('{esc(r['ip'])}'); return false;">{esc(r['ip'])}</a></td>
<td>{esc(r['hostname'])}</td>
<td><div class="mini-ports">{mini}</div></td>
<td><span class="tag tag-open">{r['qtd_portas']} porta(s)</span></td>
<td>{esc(r['_arquivo'])}</td>
</tr>"""

    return jsonify({
        "tabela": tabela,
        "info": f"Exibindo {len(resultados)} de {len(agrupados)} IPs",
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
        "porta": sorted({r["porta"].strip() for r in filtrados if r["porta"]}, key=lambda x: int(x) if x.isdigit() else 999999),
        "estado": sorted({r["estado"] for r in filtrados if r["estado"]}),
    })


@app.route("/estatisticas")
def estatisticas():
    from collections import Counter
    top_portas = Counter(r["porta"].strip() for r in DADOS if r["porta"]).most_common(10)
    top_servicos = Counter((r["servico"] or "unknown").strip() for r in DADOS).most_common(10)
    top_blocos = Counter(r["bloco"] for r in DADOS if r["bloco"]).most_common(8)
    estados = Counter((r["estado"] or "unknown").strip() for r in DADOS)

    return jsonify({
        "portas": [{"nome": k, "total": v} for k, v in top_portas],
        "servicos": [{"nome": k or "unknown", "total": v} for k, v in top_servicos],
        "blocos": [{"nome": k, "total": v} for k, v in top_blocos],
        "estados": [{"nome": k or "unknown", "total": v} for k, v in estados.items()],
    })


@app.route("/exportar")
def exportar():
    formato = request.args.get("formato", "csv")
    q = request.args.get("q", "")
    filtros = {c: request.args.get(c, "") for c in ["bloco", "servico", "porta", "estado"]}
    filtrados = filtrar(DADOS, q, filtros)

    if formato == "json":
        import json as jsonlib
        payload = [r for r in filtrados if r.get("ip")]
        nome = f"relatorio_{time.strftime('%Y%m%d_%H%M%S')}.json"
        return Response(
            jsonlib.dumps(payload, ensure_ascii=False, indent=2),
            mimetype="application/json",
            headers={"Content-Disposition": f"attachment; filename={nome}"},
        )

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(COLUNAS_EXPORT)
    for r in filtrados:
        if not r.get("ip"):
            continue
        writer.writerow([r.get(c, "") for c in COLUNAS_EXPORT])
    nome = f"relatorio_{time.strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={nome}"},
    )


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


@app.route("/ip/<ip>")
def detalhe_ip(ip):
    portas = [r for r in DADOS if r.get("ip") == ip]
    if not portas:
        return jsonify({"erro": f"IP '{ip}' nao encontrado nos dados."})

    from collections import Counter
    primeiro = portas[0]
    estados = Counter((r.get("estado") or "unknown").strip() for r in portas)
    return jsonify({
        "ip": ip,
        "hostname": primeiro.get("hostname", ""),
        "bloco": primeiro.get("bloco", ""),
        "os": primeiro.get("os", ""),
        "_arquivo": primeiro.get("_arquivo", ""),
        "estatisticas": {
            "total": len(portas),
            "open": estados.get("open", 0),
            "closed": estados.get("closed", 0),
            "filtered": estados.get("filtered", 0),
        },
        "portas": [
            {
                "porta": r.get("porta", "").strip(),
                "servico": r.get("servico", ""),
                "estado": r.get("estado", ""),
                "versao": r.get("versao", ""),
                "protocolo": r.get("protocolo", ""),
                "os": r.get("os", ""),
            }
            for r in sorted(portas, key=lambda x: int(x.get("porta", "0")) if x.get("porta", "0").strip().isdigit() else 0)
        ],
    })


if __name__ == "__main__":
    if not DADOS:
        print("Nenhum arquivo rela*.csv encontrado no diretorio atual.")
    print(f"Carregados {len(DADOS)} registros de ({', '.join(sorted({r['_arquivo'] for r in DADOS}))})")
    app.run(debug=True, host="0.0.0.0", port=5000)
