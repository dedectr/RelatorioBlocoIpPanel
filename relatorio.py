import glob
import os
import csv
import io
import time
from collections import Counter
from flask import Flask, request, jsonify, render_template_string, Response

app = Flask(__name__)

CAMPOS = ["bloco", "ip", "hostname", "os", "protocolo", "porta", "estado", "servico", "versao"]
POR_PAGINA = 50

STATUS = {"arquivos_ok": [], "arquivos_erro": [], "timestamp": None}


def carregar_dados():
    registros, ok, erro = [], [], []
    for arquivo in sorted(glob.glob("rela*.csv")):
        try:
            with open(arquivo, newline="", encoding="utf-8", errors="replace") as f:
                conteudo = f.read()
                if not conteudo.strip():
                    erro.append({"arquivo": os.path.basename(arquivo), "erro": "Arquivo vazio"})
                    continue
                f.seek(0)
                count = 0
                for linha in csv.DictReader(f, delimiter=";"):
                    linha = {k: (v.strip() if v else "") for k, v in linha.items()}
                    if not linha.get("ip"):
                        continue
                    linha["_arquivo"] = os.path.basename(arquivo)
                    registros.append(linha)
                    count += 1
                ok.append({"arquivo": os.path.basename(arquivo), "registros": count})
        except Exception as e:
            erro.append({"arquivo": os.path.basename(arquivo), "erro": str(e)})

    if not (ok or erro):
        erro.append({"arquivo": "(nenhum rela*.csv)", "erro": "Nenhum arquivo CSV no diretorio"})

    STATUS["arquivos_ok"] = ok
    STATUS["arquivos_erro"] = erro
    STATUS["timestamp"] = time.strftime("%d/%m/%Y %H:%M:%S")
    return registros


DADOS = carregar_dados()


def filtrar(dados, filtros):
    q = (filtros.get("q") or "").lower().strip()
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
        if q and not any(q in str(r[c]).lower() for c in CAMPOS):
            continue
        resultado.append(r)
    return resultado


def agrupar(dados, filtros):
    ips = {}
    for r in dados:
        ip = r.get("ip")
        if not ip:
            continue
        g = ips.setdefault(ip, {
            "ip": ip,
            "hostname": r.get("hostname", ""),
            "bloco": r.get("bloco", ""),
            "_arquivo": r.get("_arquivo", ""),
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
    # mantém apenas IPs cujas portas passam nos filtros (não carregados acima só p/ bloco)
    return list(ips.values())


def ordenar(dados, campo, direcao):
    def chave(r):
        v = r.get(campo) or ""
        return (int(v) if v.isdigit() else v.lower(), str(v))
    return sorted(dados, key=chave, reverse=(direcao < 0))


def paginar(dados, pagina):
    try:
        pagina = int(pagina)
    except (ValueError, TypeError):
        pagina = 1
    total_paginas = max(1, -(-len(dados) // POR_PAGINA))
    pagina = max(1, min(pagina, total_paginas))
    inicio = (pagina - 1) * POR_PAGINA
    return pagina, total_paginas, dados[inicio:inicio + POR_PAGINA]


def opcoes_de(dados):
    portas = sorted({r["porta"].strip() for r in dados if r["porta"]},
                    key=lambda x: int(x) if x.isdigit() else 99999)
    return {
        "bloco": sorted({r["bloco"] for r in dados if r["bloco"]}),
        "servico": sorted({r["servico"] for r in dados if r["servico"]}),
        "porta": portas,
        "estado": sorted({r["estado"] for r in dados if r["estado"]}),
    }


def ler_filtros():
    src = request.args if request.method == "GET" else request.form
    return {c: src.get(c, "") for c in ["q", "bloco", "servico", "porta", "estado"]}


def esc(v):
    return (v or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;")


def linha_tabela(r):
    mini = "".join(
        f'<span class="mini-port" title="{esc(p["servico"])} ({esc(p["estado"])})">{esc(p["porta"])}</span>'
        for p in r["portas"]
    ) or '<span class="sem-porta">sem porta</span>'
    return f"""<tr data-ip="{esc(r['ip'])}">
<td><input type="checkbox" class="sel-linha" value="{esc(r['ip'])}" onchange="atualizarSelecao()"></td>
<td>{esc(r['bloco'])}</td>
<td><a class="link-ip" href="#" onclick="abrirDetalheIP('{esc(r['ip'])}');return false;">{esc(r['ip'])}</a></td>
<td>{esc(r['hostname'])}</td>
<td><div class="mini-ports">{mini}</div></td>
<td><span class="tag tag-open">{len(r['portas'])} porta(s)</span></td>
<td>{esc(r['_arquivo'])}</td>
</tr>"""


HTML = """<!DOCTYPE html>
<html lang="pt-br" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Relatorio de Portas</title>
<style>
:root{--bg:#0f172a;--panel:#1e293b;--border:#334155;--text:#e2e8f0;--muted:#94a3b8;--accent:#38bdf8;--accent2:#0ea5e9;--hover:#263449;--shadow:rgba(0,0,0,.4);--input:#1e293b}
html[data-theme=light]{--bg:#f1f5f9;--panel:#fff;--border:#cbd5e1;--text:#1e293b;--muted:#64748b;--accent:#0284c7;--accent2:#0369a1;--hover:#f8fafc;--shadow:rgba(0,0,0,.1);--input:#fff}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif;background:var(--bg);color:var(--text);transition:background .3s,color .3s}
.container{max-width:1400px;margin:0 auto;padding:20px}
h1{text-align:center;margin-bottom:5px;color:var(--accent);font-size:26px}
.sub{text-align:center;color:var(--muted);margin-bottom:18px}
.topbar{display:flex;justify-content:flex-end;margin-bottom:15px}
.icon-btn{background:var(--panel);border:1px solid var(--border);color:var(--text);padding:8px 14px;border-radius:8px;cursor:pointer;font-size:14px}
.icon-btn:hover{border-color:var(--accent);color:var(--accent)}
.stats{display:flex;flex-wrap:wrap;gap:12px;justify-content:center;margin-bottom:18px}
.stat{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:12px 20px;text-align:center;min-width:120px}
.stat .num{font-size:24px;font-weight:bold;color:var(--accent)}
.stat .lbl{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:1px}
.status-banner{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:14px 20px;margin-bottom:18px;font-size:13px;color:var(--muted)}
.status-banner b{color:var(--text)}
.status-banner .ok{color:#86efac}.status-banner .err{color:#fca5a5}
.status-banner ul{margin-top:8px;display:none}
.status-banner button{background:none;border:1px solid var(--border);color:var(--muted);padding:3px 12px;border-radius:6px;cursor:pointer;font-size:12px;margin-top:8px}
.status-banner button:hover{border-color:var(--accent);color:var(--accent)}
.no-data{border:2px solid #dc2626;border-radius:10px;padding:30px;text-align:center;margin-bottom:20px}
.no-data h2{color:#fca5a5;margin-bottom:8px}
.search-box{display:flex;gap:10px;margin-bottom:12px;flex-wrap:wrap}
.search-box input[type=text]{flex:1;min-width:250px;padding:11px 14px;border-radius:8px;border:1px solid var(--border);background:var(--input);color:var(--text);font-size:15px}
.search-box input:focus{outline:none;border-color:var(--accent)}
.search-box button{padding:11px 18px;border:none;border-radius:8px;background:var(--accent2);color:#fff;font-size:14px;font-weight:bold;cursor:pointer}
.search-box button:hover{background:var(--accent)}
.search-box .ghost{background:var(--panel);color:var(--text);border:1px solid var(--border)}
.selects{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;margin-bottom:12px}
.selects select{padding:10px;border-radius:8px;border:1px solid var(--border);background:var(--input);color:var(--text);width:100%}
.meta{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;flex-wrap:wrap;gap:10px;font-size:14px;color:var(--muted)}
.meta .pager{display:flex;gap:6px;align-items:center}
.meta button{padding:6px 12px;border:none;border-radius:6px;background:var(--panel);color:var(--text);cursor:pointer;border:1px solid var(--border)}
.meta button:disabled{opacity:.4;cursor:not-allowed}
table{width:100%;border-collapse:collapse;background:var(--panel);border-radius:10px;overflow:hidden;box-shadow:0 4px 20px var(--shadow)}
th{background:var(--accent2);color:#fff;text-align:left;padding:11px 14px;font-size:13px;text-transform:uppercase;letter-spacing:.5px;cursor:pointer;user-select:none;white-space:nowrap}
th[data-sort]{cursor:pointer}
th.sortable:hover{background:var(--accent)}
th .arrow{font-size:10px;margin-left:5px}
td{padding:9px 14px;border-bottom:1px solid var(--border);font-size:14px;word-break:break-all}
tbody tr:hover{background:var(--hover)}
tr.selected{background:rgba(56,189,248,.12)}
.mini-ports{display:inline-flex;flex-wrap:wrap;gap:4px}
.mini-port{background:var(--panel);border:1px solid var(--border);color:var(--accent);padding:1px 7px;border-radius:12px;font-size:11px}
.sem-porta{color:var(--muted);font-size:12px}
.link-ip{color:var(--accent);cursor:pointer;text-decoration:underline}
.tag{display:inline-block;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:bold}
.tag-open{background:#166534;color:#86efac}
.empty{text-align:center;padding:40px;color:var(--muted)}
.note{text-align:center;color:var(--muted);font-size:12px;margin-top:18px}
.modal-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:1000;justify-content:center;align-items:center;padding:20px}
.modal-overlay.active{display:flex}
.modal{background:var(--panel);border:1px solid var(--border);border-radius:16px;width:100%;max-width:800px;max-height:85vh;overflow-y:auto;box-shadow:0 20px 60px rgba(0,0,0,.6)}
.modal-header{display:flex;justify-content:space-between;align-items:center;padding:18px 22px;border-bottom:1px solid var(--border);position:sticky;top:0;background:var(--panel)}
.modal-header h2{color:var(--accent);font-size:19px}
.modal-close{background:none;border:none;color:var(--muted);font-size:28px;cursor:pointer;padding:0 8px;line-height:1}
.modal-close:hover{color:#f87171}
.modal-body{padding:22px}
.ip-hero{text-align:center;margin-bottom:20px;padding:18px;background:var(--bg);border-radius:12px;border:1px solid var(--border)}
.ip-hero .addr{font-size:28px;font-weight:bold;color:var(--accent);word-break:break-all}
.ip-hero .muted{font-size:14px;color:var(--muted);margin-top:4px}
.info-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:20px}
.info-card{background:var(--bg);border:1px solid var(--border);border-radius:10px;padding:13px}
.info-card .label{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:4px}
.info-card .value{font-size:15px;font-weight:bold;word-break:break-all}
.ports-section h3{color:var(--accent);font-size:15px;margin-bottom:12px;text-transform:uppercase;letter-spacing:1px}
.port-card{background:var(--bg);border:1px solid var(--border);border-radius:10px;padding:13px;margin-bottom:9px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px}
.port-num{font-size:20px;font-weight:bold;color:#fdba74}
.port-info{flex:1;min-width:200px}
.port-svc{font-size:14px}
.port-ver{font-size:12px;color:var(--muted)}
.port-state{text-align:right}
.loading{padding:20px;text-align:center;color:var(--muted)}
@media(max-width:640px){.info-grid{grid-template-columns:1fr}.container{padding:12px}.search-box input{min-width:100%}}
</style>
</head>
<body>
<div class="container">
  <div class="topbar"><button class="icon-btn" id="btnTema">Tema</button></div>
  <h1>Relatorio de Portas</h1>
  <p class="sub">Escaneamento de servicos e portas</p>

  {% if not dados_disponiveis %}
  <div class="no-data">
    <h2>Nenhum dado disponivel</h2>
    <p>Nenhum arquivo <b>rela*.csv</b> foi encontrado ou os arquivos estao vazios. Coloque os CSVs no mesmo diretorio do script e reinicie.</p>
  </div>
  {% endif %}

  <div class="status-banner" id="statusBanner">
    {% for a in status.arquivos_ok %}<span class="ok">&#10003; {{ a.arquivo }} ({{ a.registros }})</span> &nbsp;{% endfor %}
    {% for a in status.arquivos_erro %} {% if loop.first %}<br>{% endif %}<span class="err">&#10007; {{ a.arquivo }}: {{ a.erro }}</span> {% endfor %}
    <div style="margin-top:6px;">Total: <b>{{ total }}</b> registros &middot; Carregado em {{ status.timestamp }}<button onclick="toggleStatus()">Mostrar detalhes</button></div>
    <ul id="statusDetails">
      {% for a in status.arquivos_ok %}<li>&bull; {{ a.arquivo }}: {{ a.registros }} linhas OK</li>{% endfor %}
      {% for a in status.arquivos_erro %}<li style="color:var(--err,#fca5a5)">&bull; {{ a.arquivo }}: {{ a.erro }}</li>{% endfor %}
    </ul>
  </div>

  <div class="stats">
    <div class="stat"><div class="num">{{ total }}</div><div class="lbl">Registros</div></div>
    <div class="stat"><div class="num">{{ ips }}</div><div class="lbl">IPs</div></div>
    <div class="stat"><div class="num">{{ blocos }}</div><div class="lbl">Blocos</div></div>
    <div class="stat"><div class="num">{{ arquivos }}</div><div class="lbl">CSV</div></div>
  </div>

  <div class="search-box">
    <input type="text" id="busca" placeholder="Pesquisar por IP, porta, servico, bloco, hostname, versao...">
    <button onclick="carregar(1)">Buscar</button>
    <button class="ghost" onclick="limpar()">Limpar</button>
    <button class="ghost" onclick="exportar('csv')">Exportar CSV</button>
    <button class="ghost" onclick="exportar('json')">Exportar JSON</button>
    <button class="ghost" id="btnCopiar" onclick="copiarSelecionados()" disabled>Copiar IPs (0)</button>
  </div>

  <div class="selects">
    <select id="filtro_bloco"><option value="">Todos os blocos</option></select>
    <select id="filtro_servico"><option value="">Todos os servicos</option></select>
    <select id="filtro_porta"><option value="">Todas as portas</option></select>
    <select id="filtro_estado"><option value="">Todos os estados</option></select>
  </div>

  <div class="meta">
    <div id="info">Carregando...</div>
    <label style="font-size:13px;"><input type="checkbox" id="selTodos" onchange="selecionarTodos()"> Selecionar todos</label>
    <div class="pager">
      <button id="ant" onclick="carregar(pagina-1)" disabled>&#8592; Anterior</button>
      <span>Pagina <b id="pagina_atual">1</b> de <b id="total_paginas">1</b></span>
      <button id="prox" onclick="carregar(pagina+1)" disabled>Proximo &#8594;</button>
    </div>
  </div>

  <div style="overflow-x:auto;">
    <table>
      <thead>
        <tr>
          <th style="cursor:default;width:30px;"></th>
          <th class="sortable" data-sort="bloco" onclick="ordenar('bloco')">Bloco <span class="arrow"></span></th>
          <th class="sortable" data-sort="ip" onclick="ordenar('ip')">IP <span class="arrow"></span></th>
          <th class="sortable" data-sort="hostname" onclick="ordenar('hostname')">Hostname <span class="arrow"></span></th>
          <th style="cursor:default;">Portas</th>
          <th style="cursor:default;">Estado</th>
          <th class="sortable" data-sort="_arquivo" onclick="ordenar('_arquivo')">Arquivo <span class="arrow"></span></th>
        </tr>
      </thead>
      <tbody id="corpo"></tbody>
    </table>
  </div>

  <div class="empty" id="vazio" style="display:none">Nenhum resultado encontrado.</div>
  <p class="note" id="rodape"></p>
</div>

<div class="modal-overlay" id="modalOverlay">
  <div class="modal">
    <div class="modal-header">
      <h2>Detalhes do IP</h2>
      <button class="modal-close" onclick="fecharModal()">&times;</button>
    </div>
    <div class="modal-body" id="modalBody"><div class="loading">Carregando...</div></div>
  </div>
</div>

<script>
let pagina = 1;
let ordemCampo = "ip";
let ordemDir = 1;
let selected = new Set();
let totalResultados = 0;

function readTheme(){return document.documentElement.getAttribute("data-theme")||"dark"}
document.documentElement.setAttribute("data-theme", localStorage.getItem("tema")||"dark");
document.getElementById("btnTema").onclick = () => {
  const t = readTheme()==="dark"?"light":"dark";
  document.documentElement.setAttribute("data-theme", t);
  localStorage.setItem("tema", t);
};

function toggleStatus(){const el=document.getElementById("statusDetails");el.style.display=el.style.display==="block"?"none":"block"}

function selecionarTodos(){
  const on=document.getElementById("selTodos").checked;
  document.querySelectorAll(".sel-linha").forEach(cb=>{cb.checked=on;on?selected.add(cb.value):selected.delete(cb.value)});
  atualizarSelecao();
}
function atualizarSelecao(){
  document.querySelectorAll(".sel-linha:checked").forEach(cb=>selected.add(cb.value));
  document.querySelectorAll(".sel-linha:not(:checked)").forEach(cb=>selected.delete(cb.value));
  const b=document.getElementById("btnCopiar");
  b.disabled=selected.size===0;
  b.textContent="Copiar IPs ("+selected.size+")";
  document.querySelectorAll("tr[data-ip]").forEach(tr=>tr.classList.toggle("selected",selected.has(tr.dataset.ip)));
}
async function copiarSelecionados(){
  try{await navigator.clipboard.writeText([...selected].sort().join("\\n"))}
  catch(e){const t=document.createElement("textarea");t.value=[...selected].sort().join("\\n");document.body.appendChild(t);t.select();document.execCommand("copy");t.remove()}
  const b=document.getElementById("btnCopiar"),old=b.textContent;
  b.textContent="Copiado!";setTimeout(()=>b.textContent=old,1500);
}

function obterFiltros(){return {
  q:document.getElementById("busca").value,
  bloco:document.getElementById("filtro_bloco").value,
  servico:document.getElementById("filtro_servico").value,
  porta:document.getElementById("filtro_porta").value,
  estado:document.getElementById("filtro_estado").value,
}}

function atualizarFiltros(){
  const f=obterFiltros(), body=new URLSearchParams(f);
  fetch("/opcoes",{method:"POST",body}).then(r=>r.json()).then(d=>{
    for(const campo of ["bloco","servico","porta","estado"]){
      const el=document.getElementById("filtro_"+campo), atual=el.value, lista=d[campo]||[];
      const placeholder={bloco:"Todos os blocos",servico:"Todos os servicos",porta:"Todas as portas",estado:"Todos os estados"}[campo];
      let html="<option value=''>"+placeholder+"</option>";
      lista.forEach(v=>html+="<option value='"+((v||"").replace(/'/g,"&#39;"))+"'>"+v+"</option>");
      el.innerHTML=html;
      if(lista.includes(atual)) el.value=atual;
    }
  });
}

async function carregar(pag){
  const f=obterFiltros();
  const body=new URLSearchParams(f);
  body.append("pagina", pag);
  body.append("ordemcampo", ordemCampo);
  body.append("ordemdir", ordemDir);
  const d=await (await fetch("/buscar",{method:"POST",body})).json();
  document.getElementById("corpo").innerHTML=d.tabela;
  document.getElementById("info").textContent=d.info;
  document.getElementById("pagina_atual").textContent=d.pagina;
  document.getElementById("total_paginas").textContent=d.total_paginas;
  document.getElementById("ant").disabled = d.pagina<=1;
  document.getElementById("prox").disabled = d.pagina>=d.total_paginas;
  document.getElementById("vazio").style.display = d.resultados===0?"block":"none";
  document.getElementById("selTodos").checked=false;
  selected.clear(); atualizarSelecao();
  pagina=d.pagina;
  atualizarFiltros();
}

function ordenar(campo){
  if(ordemCampo===campo) ordemDir=-ordemDir; else {ordemCampo=campo; ordemDir=1;}
  carregar(1);
}

function limpar(){
  document.getElementById("busca").value="";
  ["bloco","servico","porta","estado"].forEach(c=>document.getElementById("filtro_"+c).value="");
  carregar(1);
}

function abrirDetalheIP(ip){
  document.getElementById("modalOverlay").classList.add("active");
  document.getElementById("modalBody").innerHTML='<div class="loading">Carregando...</div>';
  fetch("/ip/"+encodeURIComponent(ip)).then(r=>r.json()).then(d=>{
    if(d.erro){document.getElementById("modalBody").innerHTML='<p class="loading">'+d.erro+'</p>';return}
    let h='<div class="ip-hero"><div class="addr">'+d.ip+'</div><div class="muted">'+(d.hostname||"Sem hostname")+'</div><div class="muted">Bloco: '+(d.bloco||"N/A")+'</div></div>';
    h+='<div class="info-grid">'
      +'<div class="info-card"><div class="label">IP</div><div class="value">'+d.ip+'</div></div>'
      +'<div class="info-card"><div class="label">Hostname</div><div class="value">'+(d.hostname||"-")+'</div></div>'
      +'<div class="info-card"><div class="label">Bloco</div><div class="value">'+(d.bloco||"-")+'</div></div>'
      +'<div class="info-card"><div class="label">Arquivo</div><div class="value">'+(d._arquivo||"-")+'</div></div>'
      +'<div class="info-card"><div class="label">Total portas</div><div class="value">'+d.estatisticas.total+'</div></div>'
      +'<div class="info-card"><div class="label">Open / Closed</div><div class="value">'+d.estatisticas.open+' / '+d.estatisticas.closed+'</div></div>'
      +'</div>';
    if(d.portas.length){h+='<div class="ports-section"><h3>Portas ('+d.portas.length+')</h3>';d.portas.forEach(p=>{h+='<div class="port-card"><div class="port-num">'+p.porta+'</div><div class="port-info"><div class="port-svc">'+(p.servico||"Desconhecido")+'</div><div class="port-ver">'+(p.versao||"N/A")+' &mdash; OS: '+(p.os||"N/A")+' &mdash; '+ (p.protocolo||"N/A")+'</div></div><div class="port-state"><span class="tag tag-open">'+(p.estado||"?")+'</span></div></div>'}) ; h+='</div>'}
    else h+='<p class="loading">Nenhuma porta registrada.</p>';
    document.getElementById("modalBody").innerHTML=h;
  }).catch(()=>{document.getElementById("modalBody").innerHTML='<p class="loading">Erro ao carregar.</p>'});
}
function fecharModal(){document.getElementById("modalOverlay").classList.remove("active")}
document.getElementById("modalOverlay").addEventListener("click",e=>{if(e.target.id==="modalOverlay")fecharModal()});
document.addEventListener("keydown",e=>{if(e.key==="Escape")fecharModal()});
document.getElementById("busca").addEventListener("keydown",e=>{if(e.key==="Enter")carregar(1)});
["bloco","servico","porta","estado"].forEach(c=>document.getElementById("filtro_"+c).addEventListener("change",()=>carregar(1)));

function exportar(formato){
  const f=obterFiltros(), p=new URLSearchParams({formato,q:f.q,bloco:f.bloco,servico:f.servico,porta:f.porta,estado:f.estado});
  window.location.href="/exportar?"+p;
}

window.addEventListener("load",()=>{carregar(1)});
</script>
</body>
</html>
"""


def total_resultados(filtros):
    return len(agrupar(filtrar(DADOS, filtros), filtros))


@app.route("/")
def index():
    filtros = ler_filtros()
    agrupados = agrupar(filtrar(DADOS, filtros), filtros)
    return render_template_string(
        HTML,
        total=len(DADOS),
        ips=len(agrupar(filtrar(DADOS, {}), {})),
        blocos=len({r["bloco"] for r in DADOS if r["bloco"]}),
        arquivos=len({r["_arquivo"] for r in DADOS}),
        status=STATUS,
        dados_disponiveis=len(DADOS) > 0,
        filtros=filtros,
    )


@app.route("/buscar", methods=["POST"])
def buscar():
    filtros = ler_filtros()
    agrupados = agrupar(filtrar(DADOS, filtros), filtros)
    agrupados = ordenar(agrupados, request.form.get("ordemcampo", "ip"), int(request.form.get("ordemdir", 1)))
    pagina, total_paginas, resultados = paginar(agrupados, request.form.get("pagina", 1))
    return jsonify({
        "tabela": "".join(linha_tabela(r) for r in resultados),
        "info": f"Exibindo {len(agrupados)} resultado(s)",
        "pagina": pagina,
        "total_paginas": total_paginas,
        "resultados": len(agrupados),
    })


@app.route("/opcoes", methods=["POST"])
def opcoes():
    filtros = ler_filtros()
    return jsonify(opcoes_de(filtrar(DADOS, filtros)))


@app.route("/ip/<ip>")
def detalhe_ip(ip):
    portas = [r for r in DADOS if r.get("ip") == ip]
    if not portas:
        return jsonify({"erro": f"IP '{ip}' nao encontrado."})
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
            for r in sorted(portas, key=lambda x: int(x.get("porta", "0")) if (x.get("porta", "") or "").strip().isdigit() else 0)
        ],
    })


@app.route("/exportar")
def exportar():
    formato = request.args.get("formato", "csv")
    filtros = ler_filtros()
    dados = [r for r in filtrar(DADOS, filtros) if r.get("ip")]
    prefixo = f"relatorio_{time.strftime('%Y%m%d_%H%M%S')}"

    if formato == "json":
        import json as jsonlib
        return Response(
            jsonlib.dumps(dados, ensure_ascii=False, indent=2),
            mimetype="application/json",
            headers={"Content-Disposition": f"attachment; filename={prefixo}.json"},
        )

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(CAMPOS)
    for r in dados:
        writer.writerow([r.get(c, "") for c in CAMPOS])
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={prefixo}.csv"},
    )


if __name__ == "__main__":
    if not DADOS:
        print("Nenhum arquivo rela*.csv encontrado no diretorio atual.")
    else:
        print(f"Carregados {len(DADOS)} registros de {', '.join(sorted({r['_arquivo'] for r in DADOS}))}")
    app.run(debug=True, host="0.0.0.0", port=5000)
