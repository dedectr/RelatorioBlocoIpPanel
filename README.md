# Site-IP

Ferramenta de escaneamento de portas e geração de relatórios web para blocos de IP.

## Como obter blocos de IP

### Usando BGP.he.net

1. Acesse [https://bgp.he.net/](https://bgp.he.net/)
2. Copei o: ASN (ex: `AS28573`) 
3. depois se coloca no site abaixo
4. Acesse [https://hackertarget.com/as-ip-lookup/](https://hackertarget.com/as-ip-lookup/)
5. Digite um ASN (ex: `AS28573`) ou um domínio e clique **Lookup**
6. Copie os blocos e adicione ao `blocos.txt`

### Formato do arquivo blocos.txt

Um bloco por linha em notação CIDR:

```
200.103.0.0/21
177.0.232.0/21
2804:d50::/28
```

Linhas que começam com `#` são ignoradas (comentários).

## Instalação

### Dependências

- **nmap** (obrigatório)
- **Python 3** (obrigatório)
- **Flask** (para a interface web)
- **ping** (opcional, usado no teste de conectividade)

### Instalar nmap

```bash
# Debian/Ubuntu
sudo apt install -y nmap

# CentOS/RHEL
sudo yum install -y nmap

# Arch
sudo pacman -S nmap
```

### Configurar o ambiente Python

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install flask
```

## Uso

### 1. Preparar os blocos

Edite `blocos.txt` e adicione os blocos de IP que deseja escanear (um por linha, formato CIDR).

### 2. Executar o scan

```bash
# Como root (recomendado - permite detecção de SO e SYN scan)
sudo ./scan_block.sh

# Ou指定 um arquivo de blocos diferente
sudo ./scan_block.sh meus_blocos.txt

# Sem root (funciona, mas sem detecção de SO)
./scan_block.sh
```

O scan gera dois arquivos:
- `relatorio_<data>.txt` - relatório completo legível
- `relatorio_<data>.csv` - base de dados (usado pela interface web)

### 3. Iniciar a interface web

```bash
source .venv/bin/activate
python relatorio.py
```

Acesse `http://localhost:5000` no navegador.

A interface permite:
- Buscar por IP, porta, serviço, hostname ou versão
- Filtrar por bloco, serviço, porta e estado
- Ordenar colunas clicando no cabeçalho
- Paginação dos resultados

## Estrutura do projeto

```
site-ip/
├── blocos.txt          # Lista de blocos IP para escanear
├── scan_block.sh       # Script de escaneamento (nmap)
├── relatorio.py        # Interface web (Flask)
├── relatorio_*.csv     # Relatórios gerados (git ignored)
├── .venv/              # Ambiente virtual Python
└── README.md
```
