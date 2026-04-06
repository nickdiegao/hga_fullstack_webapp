# HGA Chamados - projeto web completo

Projeto full stack para hospedagem web com frontend e backend em Flask.

## Recursos já incluídos

- abertura pública de chamados
- login por perfil: master, admin e empresa
- empresa só visualiza e atualiza os próprios chamados
- protocolo curto (`HGA-001`, `HGA-002`...)
- tema claro/escuro
- logomarca e créditos configuráveis pelo master
- WhatsApp opcional, sem SMS
- opção `Outros` para empresa responsável
- relatório com impressão/PDF via navegador
- filtro de empresas pendentes para admin/master
- usuário comum não edita nome de exibição
- senha com hash seguro
- telefone e empresa “outros” protegidos com criptografia em repouso no banco

## Estrutura

- `app.py` - backend Flask
- `templates/` - frontend renderizado no servidor
- `static/` - CSS e uploads da logomarca
- `instance/app.db` - banco SQLite criado automaticamente
- `.env.example` - variáveis principais
- `Dockerfile` - imagem simples para deploy

## Requisitos

- Python 3.11+ (recomendado 3.12)

## Como rodar localmente

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Abra no navegador:

```text
http://localhost:5000
```

## Usuários iniciais

- master / `hgaMaster@2026`
- admin / `admin123`
- empresa1 / `123456`
- empresa2 / `123456`
- empresa3 / `123456`

## Deploy simples

### Gunicorn

```bash
pip install gunicorn
SECRET_KEY='troque-uma-chave-forte' gunicorn -w 2 -b 0.0.0.0:5000 app:app
```

### Docker

```bash
docker build -t hga-chamados .
docker run -p 5000:5000 -e SECRET_KEY='troque-uma-chave-forte' -e FIXED_YEAR=2026 hga-chamados
```

## Observações de segurança

- este pacote melhora bastante a segurança do protótipo HTML
- para produção pública, use HTTPS, proxy reverso e backup do banco
- SQLite funciona bem para operação pequena; para escala maior, troque para PostgreSQL
- para logs de auditoria, MFA e envio oficial via WhatsApp Business API, é recomendável uma próxima etapa
