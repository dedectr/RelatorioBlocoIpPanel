#!/bin/bash

# ============================================================
#  scan_block.sh - Relatorio completo de IPs ativos por bloco
#
#  Uso: ./scan_block.sh [arquivo_de_blocos]
#
#  Gera:
#    relatorio_<data>.txt  - relatorio completo legivel
#    relatorio_<data>.csv  - base de dados (1 linha por porta)
# ============================================================

ARQ_ENTRADA="${1:-blocos.txt}"
HORA="$(date +%Y%m%d_%H%M%S)"
BASE="relatorio_${HORA}"
ARQ_TXT="${BASE}.txt"
ARQ_CSV="${BASE}.csv"
TMP="/tmp/scan_block_${HORA}"

# --------------------- config ------------------------------
RESOLVER_DNS="on"        # "off" = usa -n (discovery mais rapido, sem hostname)
TOP_PORTAS=15            # qtd de portas no resumo geral
TOP_SERVICOS=15          # qtd de servicos no resumo geral
TOP_SO=15                # qtd de dist. por SO no resumo geral
TESTAR_CONECTIVIDADE="on" # "on" = ping de teste antes de escanear cada bloco
PINGS_POR_IP=2           # qtd de pings por host de teste
TIMEOUT_PING=1           # timeout (s) de cada ping
# -----------------------------------------------------------

mkdir -p "$TMP" || exit 1
trap 'rm -rf "$TMP"' EXIT
SECONDS=0

# --------------------- pre-checagens -----------------------
if [ ! -f "$ARQ_ENTRADA" ]; then
    echo "Erro: arquivo '$ARQ_ENTRADA' nao encontrado."
    echo "Use: $0 [arquivo_de_blocos]"
    exit 1
fi

if ! command -v nmap >/dev/null 2>&1; then
    echo "Erro: nmap nao esta instalado."
    exit 1
fi

# --------------------- privilegios -------------------------
if [ "$(id -u)" -eq 0 ]; then
    NMAP="nmap"
    EXTRA="-sS -O"
    MODO="root"
    DETECTA_SO="sim"
else
    if sudo -n true >/dev/null 2>&1; then
        NMAP="sudo -n nmap"
        EXTRA="-sS -O"
        MODO="root (via sudo sem senha)"
        DETECTA_SO="sim"
    else
        NMAP="nmap"
        EXTRA="-sT"                 # connect scan, sem precisar de root
        MODO="usuario"
        DETECTA_SO="nao"
    fi
fi

DNSARG=""
[ "$RESOLVER_DNS" = "off" ] && DNSARG="-n"

TOTAL_BLOCOS="$(grep -vcE '^\s*#|^\s*$' "$ARQ_ENTRADA")"
[ "$TOTAL_BLOCOS" -eq 0 ] && { echo "Erro: arquivo de blocos vazio."; exit 1; }

# contadores globais (atualizados durante o loop)
TOTAL_HOSTS=0
TOTAL_PORTAS=0
TOTAL_HOSTS_COM_PORTA=0
TOTAL_BLOCOS_SEM_CONEXAO=0

# --------------------- arquivos de saida -------------------
> "$TMP/corpo.txt"
> "$TMP/resumo_raw.txt"
{
    echo "=========================================================================="
    echo "  RELATORIO COMPLETO - SCAN DE REDE"
    echo "=========================================================================="
    echo "  Gerado em        : $(date '+%d/%m/%Y %H:%M:%S %Z')"
    echo "  Arquivo de blocos: $ARQ_ENTRADA"
    echo "  Blocos a analisar: $TOTAL_BLOCOS"
    echo "  Modo de execucao : $MODO"
    echo "  Deteccao de SO   : $DETECTA_SO"
    echo "  Escaneamento     : $NMAP -sV --version-light --open $EXTRA"
    echo "--------------------------------------------------------------------------"
    echo "  CONVENCOES:"
    echo "   [+]  IP/host ativo"
    echo "   porta/proto  estado  servico  versao"
    echo "=========================================================================="
    echo
} > "$TMP/cabecalho.txt"

printf 'bloco;ip;hostname;os;protocolo;porta;estado;servico;versao\n' > "$ARQ_CSV"

# --------------------- parser do -oG -----------------------
cat > "$TMP/parser.awk" <<'AWK'
BEGIN { FS = "\t"; cnt = 0 }

/^Host: / {
    ip = ""; host = ""; os = ""; ports = ""; status = ""
    n = split($0, f, "\t")
    for (i = 1; i <= n; i++) {
        fi = f[i]
        if (fi ~ /^Host: /) {
            h = substr(fi, 7)
            sub(/^ +/, "", h)
            if (h ~ /^\[/) {
                c = index(h, "]")
                ip = substr(h, 2, c - 2)
            } else {
                split(h, a, " ")
                ip = a[1]
            }
        } else if (fi ~ /^Ports: /) {
            ports = substr(fi, 8)
        } else if (fi ~ /^Status: /) {
            status = substr(fi, 8)
        } else if (fi ~ /^OS: /) {
            os = substr(fi, 5)
        }
    }
    if (ip == "") next
    key = ip

    # hostname somente se vier no campo "Host:" entre parenteses (e nao for um IP)
    if (h != "" && match(h, /\([^)]*\)/) > 0) {
        hn = substr(h, RSTART + 1, RLENGTH - 2)
        if (hn != "" && hn !~ /^[0-9a-f:.]+$/) host = hn
    }

    if (key in seen) {
        if (ports != "") plist[key] = ports
        if (os != "")    olist[key] = os
        if (host != "")  hlist[key] = host
        next
    }
    seen[key] = 1
    iplist[++cnt] = ip
    hlist[key] = host
    olist[key] = os
    plist[key] = ports
}

END {
    total_open = 0
    for (k = 1; k <= cnt; k++) {
        ip = iplist[k]
        line = sprintf("  [%s] %-21s", "+", ip)
        line = line sprintf( (hlist[ip] != "" ? " %-32s" : " %-32s"), (hlist[ip] != "" ? "(" hlist[ip] ")" : ""))
        if (mode == "root") {
            os_txt = (olist[ip] != "" ? olist[ip] : "nao detectado")
            gsub(/\|/, " / ", os_txt)
            line = line sprintf("OS: %s", os_txt)
        } else {
            line = line "OS: indisponivel (sem root)"
        }
        print line
        ports = plist[ip]
        if (ports == "") {
            print "        Nenhuma porta aberta."
            continue
        }
        np = split(ports, ps, ",")
        nopen = 0
        for (j = 1; j <= np; j++) {
            if (ps[j] !~ /\/open\//) continue
            nopen++
            nf = split(ps[j], e, "/")
            porta = e[1]; est = e[2]; proto = e[3]; serv = e[5]; ver = ""
            for (q = 6; q <= nf; q++) if (e[q] != "") ver = (ver == "" ? e[q] : ver " " e[q])
            if (serv == "") serv = "desconhecido"
            printf "        %-8s %-6s %-14s %s\n", porta "/" proto, est, serv, ver
            printf "%s;%s;%s;%s;%s;%s;%s;%s;%s\n",
                   bloco, ip, hlist[ip], (olist[ip] != "" ? olist[ip] : ""),
                   proto, porta, est, serv, ver >> csv
        }
        total_open += nopen
        if (nopen == 0) print "        Nenhuma porta aberta."
    }
    printf "  Total de portas abertas no bloco: %d\n\n", total_open
}
AWK

echo "Processando $TOTAL_BLOCOS blocos de '$ARQ_ENTRADA' ..."
echo "Relatorio: $ARQ_TXT   |   Base CSV: $ARQ_CSV"
echo

# --------------------- teste de conectividade --------------
# Retorna 0 se o bloco respondeu a ao menos um host de teste,
# 1 caso contrario. Usa ping quando disponivel, senao nmap -sn.
testar_bloco() {
    local bloco="$1" i alvo ok=1
    local IP=()
    local alvo6=""

    if [[ "$bloco" == *":"* ]]; then
        alvo6="${bloco%%/*}"
        if command -v ping >/dev/null 2>&1; then
            for i in $(seq "$PINGS_POR_IP"); do
                ping -6 -c 1 -W "$TIMEOUT_PING" "$alvo6" >/dev/null 2>&1 && ok=0
            done
            return $ok
        fi
        $NMAP -6 -sn -n -T4 "$alvo6" 2>/dev/null | grep -q "Nmap scan report for" && return 0
        return 1
    fi

    if command -v python3 >/dev/null 2>&1; then
        while IFS= read -r a; do [ -n "$a" ] && IP+=("$a"); done < <(
            python3 - "$bloco" <<'PY'
import sys, ipaddress
try:
    n = ipaddress.ip_network(sys.argv[1], strict=False)
except Exception:
    sys.exit()
ip = int(n.network_address)
for i in range(1, min(4, n.num_addresses)):
    print(ipaddress.IPv4Address(ip + i))
PY
        )
    fi

    if [ "${#IP[@]}" -eq 0 ]; then
        alvo="${bloco%%/*}"
        IP=("$alvo" "${alvo%.*}.1" "${alvo%.*}.254")
    fi

    if command -v ping >/dev/null 2>&1; then
        for i in "${IP[@]}"; do
            if ping -c "$PINGS_POR_IP" -W "$TIMEOUT_PING" "$i" >/dev/null 2>&1; then
                return 0
            fi
        done
    else
        $NMAP -sn -n -T4 --max-retries 1 "${IP[@]}" 2>/dev/null \
            | grep -q "Nmap scan report for" && return 0
    fi
    return 1
}

NUM_BLOCO=0
while IFS= read -r bloco; do
    bloco="$(echo "$bloco" | xargs)"
    [ -z "$bloco" ] && continue
    case "$bloco" in
        \#*) continue ;;
    esac
    NUM_BLOCO=$((NUM_BLOCO + 1))

    if [[ "$bloco" == *":"* ]]; then F6="-6"; else F6=""; fi

    echo "[$NUM_BLOCO/$TOTAL_BLOCOS] Bloco: $bloco ..."

    # ---------------- 1) checagem de conectividade -------------
    CONECTIVIDADE="ok"
    if [ "$TESTAR_CONECTIVIDADE" = "on" ]; then
        if testar_bloco "$bloco"; then
            echo "    Conectividade: OK (resposta ao ping)"
        else
            CONECTIVIDADE="sem resposta"
            TOTAL_BLOCOS_SEM_CONEXAO=$((TOTAL_BLOCOS_SEM_CONEXAO + 1))
            echo "    Conectividade: SEM RESPOSTA - pulando bloco"
            {
                echo "=========================================================================="
                echo "BLOCO: $bloco"
                echo "=========================================================================="
                echo "  Conectividade: SEM RESPOSTA (teste de ping falhou)"
                echo "  Bloco pulado (nenhum scan executado)."
                echo "=========================================================================="
                echo
            } >> "$TMP/corpo.txt"
            continue
        fi
    fi

    # ---------------- 2) descoberta de hosts ativos --------------
    $NMAP $DNSARG -sn -T4 $F6 "$bloco" 2>/dev/null \
        | grep "Nmap scan report for" \
        | awk '{ for (i=1;i<=NF;i++) { t=$i; gsub(/[()]/,"",t); if (t ~ /^[0-9a-f:.]+$/) { print t; break } } }' \
        | sort -u -V > "$TMP/hosts.txt"

    N_HOSTS="$(wc -l < "$TMP/hosts.txt")"
    echo "    Hosts ativos: $N_HOSTS"
    TOTAL_HOSTS=$((TOTAL_HOSTS + N_HOSTS))

    {
        echo "=========================================================================="
        echo "BLOCO: $bloco"
        echo "=========================================================================="
        echo "  Hosts ativos: $N_HOSTS"
        echo
    } >> "$TMP/corpo.txt"

    if [ "$N_HOSTS" -eq 0 ]; then
        {
            echo "  Nenhum host ativo encontrado."
            echo "=========================================================================="
            echo
        } >> "$TMP/corpo.txt"
        continue
    fi

    # ---------------- 3) scan detalhado (portas/servicos) -------
    $NMAP $DNSARG -sV --version-light --open -T4 $F6 $EXTRA \
        -oG "$TMP/portas.txt" -iL "$TMP/hosts.txt" > "$TMP/scan_log.txt" 2>&1

    awk -v bloco="$bloco" -v mode="$MODO" -v csv="$ARQ_CSV" \
        -f "$TMP/parser.awk" "$TMP/portas.txt" >> "$TMP/corpo.txt"

done < "$ARQ_ENTRADA"

# --------------------- resumo geral --------------------------
TOTAL_PORTAS="$(awk -F';' 'NR>1 {n++} END{print n+0}' "$ARQ_CSV")"
TOTAL_HOSTS_COM_PORTA="$(awk -F';' 'NR>1 {p[$2]++} END{print length(p)}' "$ARQ_CSV")"
PORTAS_DISTINTAS="$(awk -F';' 'NR>1 {p[$6"/"$5]++} END{print length(p)}' "$ARQ_CSV")"
HOSTS_SEM_PORTA=$((TOTAL_HOSTS - TOTAL_HOSTS_COM_PORTA))
[ "$HOSTS_SEM_PORTA" -lt 0 ] && HOSTS_SEM_PORTA=0

DURACAO="$(date -u -d "@$SECONDS" +%H:%M:%S)"

{
    echo "=========================================================================="
    echo "  RESUMO GERAL"
    echo "=========================================================================="
    echo "  Blocos processados      : $TOTAL_BLOCOS"
    echo "  Blocos sem conectividade: $TOTAL_BLOCOS_SEM_CONEXAO"
    echo "  Hosts ativos            : $TOTAL_HOSTS"
    echo "  Hosts com porta aberta  : $TOTAL_HOSTS_COM_PORTA"
    echo "  Hosts sem porta aberta  : $HOSTS_SEM_PORTA"
    echo "  Portas abertas (total)  : $TOTAL_PORTAS"
    echo "  Portas distintas        : $PORTAS_DISTINTAS"
    echo "  Tempo total             : $DURACAO"
    echo
    echo "  TOP PORTAS ABERTAS"
    echo "  -------------------"
    awk -F';' 'NR>1 {p[$6"/"$5]++} END{for (x in p) printf "%8d  %s\n", p[x], x}' "$ARQ_CSV" \
        | sort -rn | head -n "$TOP_PORTAS" | awk '{printf "    %s\n", $0}'
    echo
    echo "  SERVICOS MAIS COMUNS"
    echo "  --------------------"
    awk -F';' 'NR>1 && $8!="" {s[$8]++} END{for (x in s) printf "%8d  %s\n", s[x], x}' "$ARQ_CSV" \
        | sort -rn | head -n "$TOP_SERVICOS" | awk '{printf "    %s\n", $0}'
    if [ "$DETECTA_SO" = "sim" ]; then
        echo
        echo "  DISTRIBUICAO POR SO"
        echo "  ---------------------"
        awk -F';' 'NR>1 && $4!="" {o[$4]++} END{for (x in o) printf "%8d  %s\n", o[x], x}' "$ARQ_CSV" \
            | sort -rn | head -n "$TOP_SO" | awk '{printf "    %s\n", $0}'
    else
        echo
        echo "  (Deteccao de SO indisponivel sem root. Execute como root/ sudo apt install -y ...)"
    fi
    echo "=========================================================================="
    echo "  Fim do relatorio. Base CSV em: $ARQ_CSV"
    echo "=========================================================================="
} > "$TMP/resumo.txt"

# --------------------- monta arquivo final -------------------
cat "$TMP/cabecalho.txt" "$TMP/corpo.txt" "$TMP/resumo.txt" > "$ARQ_TXT"

echo
echo "============================================"
echo " Scan finalizado em $DURACAO."
echo " Hosts ativos: $TOTAL_HOSTS | Portas abertas: $TOTAL_PORTAS"
echo " Relatorio : $ARQ_TXT"
echo " Base CSV  : $ARQ_CSV"
echo "============================================"