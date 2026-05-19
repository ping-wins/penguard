# Configuração do SSO Kerberos (Active Directory + Keycloak)

Este guia descreve, passo a passo, tudo que precisa estar configurado para o
botão **"Login with SSO (Kerberos)"** funcionar na cockpit do Penguard.
A integração faz o navegador apresentar um ticket Kerberos para o Keycloak
(SPNEGO), o Keycloak valida contra o KDC do Active Directory e o BFF
(`apps/api`) abre a sessão HTTP-only via Authorization Code flow.

> ⚠️ Tudo aqui é **lab**. Não use `HTTP://` (sem TLS), `allowWeakCrypto`,
> `dev-client-secret`, nem usuários `admin/admin` em produção.

---

## 1. Visão geral do fluxo

```
[Workstation Windows ingressada no domínio]
        │  1. Ticket Kerberos (TGS) HTTP/penguard.local
        ▼
[Browser  ────── SPNEGO ──────► Keycloak (Authorization Endpoint)]
        ▲                              │
        │                              │ 2. Valida ticket usando o keytab + krb5.conf
        │                              ▼
        │                       [AD DC — KDC PENGUARD.LOCAL]
        │                              │
        │  3. Code OAuth2 (302)        │
        │ ◄────────────────────────────┘
        ▼
[BFF /api/auth/sso/kerberos/callback]
        │  4. Token exchange (client_id + client_secret)
        ▼
[Keycloak Token Endpoint] ──► ID Token + refresh
        │
        ▼
[BFF cria sessão HTTP-only e redireciona para o frontend]
```

Hosts envolvidos no lab atual:

| Componente | Host / IP                                       | Porta          |
|------------|-------------------------------------------------|----------------|
| AD DC      | `dc01.penguard.local` (`192.168.56.10`)   | 88 (TCP/UDP), 389, 464 |
| Keycloak   | `penguard.local` (host Docker)            | 8080 (interno) → 8080 (publicado) |
| BFF API    | `penguard.local`                          | 8000           |
| Web/Vite   | `penguard.local`                          | 5173           |

> Os valores acima vêm de `krb5.conf`, `docker-compose.yml` e
> `infra/keycloak/realm-penguard.json`. Se você mudar qualquer um deles,
> atualize todos juntos — Kerberos é implacável com inconsistência.

---

## 2. Pré-requisitos

### No Windows Server (AD DC)

- Windows Server 2019 ou 2022 com a role **Active Directory Domain Services**
  promovida.
- Domain / Realm: `PENGUARD.LOCAL` (Forest Functional Level ≥ 2016).
- IP estático para o DC: `192.168.56.10` (ou ajuste `krb5.conf` e os
  `extra_hosts` do Docker).
- Conta de domínio com privilégio para criar usuários, definir SPN e exportar
  keytab (Domain Admin durante o setup; depois pode rebaixar).

### Na máquina que roda o Docker (Keycloak + BFF)

- Docker Desktop ou Docker Engine + Compose v2.
- Resolução de `penguard.local` para o host (ver passo 6).
- Acesso de rede ao DC nas portas 88/389/464 TCP+UDP.

### Na workstation que vai usar o SSO

- Windows ingressada no domínio `PENGUARD.LOCAL` **ou** com ticket
  Kerberos válido (`klist` mostra o TGT).
- Browser com Integrated Windows Authentication habilitada para a zona
  Intranet (ou Firefox com `network.negotiate-auth.trusted-uris` configurado —
  ver passo 7).

---

## 3. Configuração do Active Directory / Windows Server

Execute como Domain Admin no DC.

### 3.1 Criar a conta de serviço do Keycloak

Crie um usuário de domínio dedicado para representar o serviço HTTP do
Keycloak. **Não** reutilize uma conta de usuário humano.

```powershell
# PowerShell elevado no DC
New-ADUser `
  -Name "svc-keycloak" `
  -SamAccountName "svc-keycloak" `
  -UserPrincipalName "svc-keycloak@PENGUARD.LOCAL" `
  -AccountPassword (Read-Host -AsSecureString "Senha do svc-keycloak") `
  -Enabled $true `
  -PasswordNeverExpires $true `
  -CannotChangePassword $true
```

Marque a conta como sensível a delegação restrita (opcional, mas recomendado):

```powershell
Set-ADUser svc-keycloak -KerberosEncryptionType "AES128,AES256"
```

### 3.2 Registrar o SPN `HTTP/penguard.local`

O SPN precisa bater **exatamente** com o `serverPrincipal` configurado no
Keycloak (`HTTP/penguard.local@PENGUARD.LOCAL`).

```powershell
# Lista SPNs já registrados (deve estar vazio para HTTP/penguard.local)
setspn -Q HTTP/penguard.local

# Registra o SPN na conta de serviço
setspn -S HTTP/penguard.local svc-keycloak
```

Se aparecer `Duplicate SPN found`, o SPN está em outra conta — remova com
`setspn -D HTTP/penguard.local <outraConta>` antes de seguir.

### 3.3 Gerar o keytab `penguard.keytab`

`ktpass` mapeia o SPN para a conta + senha e produz o keytab que o Keycloak
vai carregar. Rode no DC (precisa do RSAT/`ktpass.exe`):

```powershell
ktpass `
  -princ HTTP/penguard.local@PENGUARD.LOCAL `
  -mapuser svc-keycloak@PENGUARD.LOCAL `
  -pass <SenhaDoSvcKeycloak> `
  -crypto AES256-SHA1 `
  -ptype KRB5_NT_PRINCIPAL `
  -out C:\Temp\penguard.keytab
```

> O atributo `userPrincipalName` da conta vira `HTTP/penguard.local`
> depois do `ktpass`. Isso é esperado; **não** edite na mão.

Se quiser fallback para AES128 (caso o Java do Keycloak reclame), gere um
segundo keytab com `-crypto AES128-SHA1` e mescle com `ktab -k <arquivo> -a`,
ou rode `ktpass` uma vez com `-crypto All`.

### 3.4 Permitir os enctypes na conta

```powershell
Set-ADUser svc-keycloak `
  -KerberosEncryptionType "AES128,AES256"
```

Se ainda usar clientes legados (Windows 7, FortiGate antigo), inclua também
`RC4` — mas no Keycloak prefira AES.

### 3.5 DNS

Crie um registro **A** no DNS do domínio apontando `penguard.local` para
o IP da máquina que roda o Keycloak:

```powershell
Add-DnsServerResourceRecordA `
  -ZoneName "penguard.local" `
  -Name "@" `
  -IPv4Address 192.168.56.20 `
  -CreatePtr
```

> Reverse DNS (`PTR`) é obrigatório para SPNEGO em alguns clientes. Confirme
> com `nslookup -type=PTR 192.168.56.20`.

### 3.6 Transferir o keytab para a máquina do Docker

Copie `C:\Temp\penguard.keytab` para a raiz do repositório do
Penguard:

```
<repo>\penguard.keytab
```

O arquivo **não pode ser commitado** — `.gitignore` já cobre `*.keytab` e
`penguard.keytab` explicitamente. Verifique antes de empurrar:

```bash
git status --ignored | grep keytab
```

---

## 4. Configuração do Keycloak

O realm de dev já vem prontinho em
`infra/keycloak/realm-penguard.json` e é importado automaticamente pelo
container (`--import-realm`). Os pontos relevantes:

### 4.1 Realm

| Campo                  | Valor                              |
|------------------------|------------------------------------|
| `realm`                | `penguard`                   |
| `loginWithEmailAllowed`| `true`                             |
| `registrationAllowed`  | `false` (criação via BFF)          |
| Roles                  | `analyst`, `admin`                 |

### 4.2 Client OAuth2 (`penguard-bff`)

| Campo            | Valor                                                                 |
|------------------|-----------------------------------------------------------------------|
| `clientId`       | `penguard-bff`                                                  |
| `publicClient`   | `false` (confidencial; client_secret obrigatório)                     |
| `protocol`       | `openid-connect`                                                      |
| `secret`         | `dev-client-secret` (substituir em produção)                          |
| `standardFlowEnabled` | `true` (Authorization Code)                                      |
| `redirectUris`   | `http://localhost:8000/api/auth/sso/kerberos/callback`, `http://api:8000/api/auth/sso/kerberos/callback`, `http://penguard.local:8000/api/auth/sso/kerberos/callback` |
| `webOrigins`     | `http://localhost:5173`, `http://penguard.local:5173`            |

> Sempre que mudar `PENGUARD_SSO_REDIRECT_URI`, adicione a nova URL em
> `redirectUris`. O Keycloak rejeita callbacks fora da allowlist.

### 4.3 User Federation — Kerberos provider

Bloco já existente no realm import (`components.org.keycloak.storage.UserStorageProvider`):

| Campo                       | Valor                                                  |
|-----------------------------|--------------------------------------------------------|
| `name`                      | `kerberos-penguard`                              |
| `providerId`                | `kerberos`                                             |
| `kerberosRealm`             | `PENGUARD.LOCAL`                                 |
| `serverPrincipal`           | `HTTP/penguard.local@PENGUARD.LOCAL`       |
| `keyTab`                    | `/opt/keycloak/conf/penguard.keytab`             |
| `allowPasswordAuthentication` | `false` (apenas SPNEGO)                              |
| `editMode`                  | `UNSYNCED` (não sobrescreve LDAP)                      |
| `cachePolicy`               | `DEFAULT`                                              |

### 4.4 Authentication Flow

Para o SPNEGO disparar antes da tela de login, o flow **Browser** precisa ter
o execution `Kerberos` marcado como **Alternative** (ou **Required**). No
import já vem assim; se editar via UI, faça:

1. Admin Console → **Authentication** → flow `browser`.
2. Action → **Add execution** → `Kerberos`.
3. Marque como **Alternative** e mova acima de `Username Password Form`.

### 4.5 Container do Keycloak

`docker-compose.yml` monta um placeholder de keytab por padrão para que o
stack local suba em Linux/Windows antes do lab AD existir. Para testar SSO de
verdade, defina `PENGUARD_KEYTAB_PATH=./penguard.keytab` no `.env`
depois de gerar/copiar o keytab real.

```yaml
keycloak:
  image: quay.io/keycloak/keycloak:26.4
  command: start-dev --import-realm --http-port=8080
  environment:
    KRB5_CONFIG: /etc/krb5.conf
    JAVA_OPTS_APPEND: >-
      -Dsun.security.krb5.allowWeakCrypto=true
      -Djava.security.krb5.conf=/etc/krb5.conf
      -Djava.security.properties=/opt/keycloak/conf/java-security-override.properties
  extra_hosts:
    - "penguard.local:192.168.56.10"
    - "dc01.penguard.local:192.168.56.10"
  volumes:
    - ./infra/keycloak/realm-penguard.json:/opt/keycloak/data/import/realm-penguard.json:ro
    - ${PENGUARD_KEYTAB_PATH:-./infra/keycloak/empty-keytab.placeholder}:/opt/keycloak/conf/penguard.keytab:ro
    - ./krb5.conf:/etc/krb5.conf:ro
    - ./infra/keycloak/java-security-override.properties:/opt/keycloak/conf/java-security-override.properties:ro
```

`java-security-override.properties` reabilita algoritmos legados de Kerberos
para o lab — **remova em produção** e cubra os clientes com AES256 puro.

---

## 5. `krb5.conf` no host Docker

Conteúdo de `krb5.conf` (já versionado, ajuste IPs se mudar de lab):

```ini
[libdefaults]
    default_realm = PENGUARD.LOCAL
    dns_lookup_realm = false
    dns_lookup_kdc = false
    rdns = false
    ticket_lifetime = 24h
    renew_lifetime = 7d
    forwardable = true
    udp_preference_limit = 0
    default_ccache_name = FILE:/tmp/krb5cc_%{uid}
    allow_weak_crypto = true
    default_tkt_enctypes = aes256-cts-hmac-sha1-96 aes128-cts-hmac-sha1-96 rc4-hmac
    default_tgs_enctypes = aes256-cts-hmac-sha1-96 aes128-cts-hmac-sha1-96 rc4-hmac
    permitted_enctypes = aes256-cts-hmac-sha1-96 aes128-cts-hmac-sha1-96 rc4-hmac

[realms]
    PENGUARD.LOCAL = {
        kdc = 192.168.56.10
        admin_server = 192.168.56.10
        default_domain = penguard.local
    }

[domain_realm]
    penguard.local = PENGUARD.LOCAL
    .penguard.local = PENGUARD.LOCAL
```

Pontos importantes:

- `kdc = <IP do DC>`: sem DNS de SRV records configurado, o Keycloak não
  descobre o KDC sozinho.
- `rdns = false`: evita que o Java tente resolver o IP do KDC de volta para
  hostname e quebre o SPN.
- `allow_weak_crypto = true` + RC4: **apenas lab**.

---

## 6. Variáveis de ambiente do BFF / Frontend

Crie/edite `.env` na raiz a partir de `.env.example` e force os hostnames
para `penguard.local` (case-sensitive nas URLs):

```env
PENGUARD_KEYCLOAK_BASE_URL=http://localhost:8080
PENGUARD_KEYCLOAK_INTERNAL_BASE_URL=http://keycloak:8080
PENGUARD_KEYCLOAK_BROWSER_BASE_URL=http://penguard.local:8080
PENGUARD_KEYCLOAK_REALM=penguard
PENGUARD_KEYCLOAK_CLIENT_ID=penguard-bff
PENGUARD_KEYCLOAK_CLIENT_SECRET=dev-client-secret
PENGUARD_KEYTAB_PATH=./penguard.keytab
PENGUARD_OIDC_ISSUER=http://penguard.local:8080/realms/penguard
PENGUARD_SSO_REDIRECT_URI=http://penguard.local:8000/api/auth/sso/kerberos/callback
PENGUARD_SSO_POST_LOGIN_URL=http://penguard.local:5173/
PENGUARD_MOCK_MODE=false
```

No Docker Compose, `PENGUARD_KEYCLOAK_INTERNAL_BASE_URL` deve continuar
apontando para `http://keycloak:8080`. Apenas as URLs usadas pelo navegador
devem trocar para `penguard.local`, porque o SPN Kerberos depende desse
hostname.

> `PENGUARD_MOCK_MODE=true` força o fluxo SSO a retornar
> `sso_error=mock_mode` para não quebrar dev offline. Mantenha `false` quando
> for testar Kerberos de verdade.

### Resolução de `penguard.local` no host Docker

- **Windows / macOS**: adicione a linha em `C:\Windows\System32\drivers\etc\hosts`
  ou `/etc/hosts` apontando para `127.0.0.1` (Docker Desktop traduz para o
  gateway):

  ```
  127.0.0.1   penguard.local
  ```

- **Linux**: o compose já usa `extra_hosts: penguard.local:host-gateway`
  para os containers; no host, adicione `127.0.0.1 penguard.local` em
  `/etc/hosts`.

---

## 7. Configuração da workstation cliente

A workstation precisa entregar SPNEGO ao Keycloak. Sem isso o flow cai no
formulário de usuário/senha.

### Edge / Chrome (Windows ingressada no domínio)

Group Policy → **Computer Configuration → Administrative Templates →
Microsoft Edge → HTTP authentication**:

| Política                                | Valor                                  |
|-----------------------------------------|----------------------------------------|
| `AuthServerAllowlist`                   | `penguard.local`                 |
| `AuthNegotiateDelegateAllowlist`        | `penguard.local` (opcional)      |
| `AmbientAuthenticationInPrivateModesEnabled` | `Regular sessions only`           |

Aplicação imediata:

```powershell
gpupdate /force
```

Confirme com `edge://policy` que `AuthServerAllowlist` está populado.

### Firefox

`about:config`:

```
network.negotiate-auth.trusted-uris = http://penguard.local
network.negotiate-auth.delegation-uris = http://penguard.local
network.auth.use-sspi = true
```

### Linux client (opcional)

```bash
sudo apt install krb5-user
sudo cp <repo>/krb5.conf /etc/krb5.conf
kinit usuario@PENGUARD.LOCAL
klist  # deve mostrar TGT válido
```

Firefox no Linux usa o mesmo `network.negotiate-auth.trusted-uris`.

---

## 8. Smoke test

1. Sobe a stack:

   ```bash
   docker compose up -d --build
   ```

2. Aguarda o Keycloak ficar saudável:

   ```bash
   curl -s http://penguard.local:8080/health/ready
   ```

3. No DC ou em uma workstation com `kinit`:

   ```bash
   kvno HTTP/penguard.local@PENGUARD.LOCAL
   ```

   Tem que retornar um `kvno` (Key Version Number) — significa que o KDC
   reconhece o SPN.

4. No browser ingressado no domínio, abra
   `http://penguard.local:5173/login` e clique em **Login with SSO
   (Kerberos)**. O fluxo esperado:

   - Redireciona para `http://penguard.local:8080/realms/penguard/protocol/openid-connect/auth?...`
   - Keycloak responde 200 imediatamente (sem formulário) e redireciona
     para `/api/auth/sso/kerberos/callback?code=...&state=...`.
   - BFF cria a sessão e manda você para `http://penguard.local:5173/`.

5. Confira o audit trail: `Sidebar → History` deve mostrar uma linha
   `Login succeeded` com `action=sso_kerberos` e outcome `success`.

---

## 9. Troubleshooting

| Sintoma                                                              | Causa provável                                                                 | Como confirmar / corrigir                                                                                  |
|----------------------------------------------------------------------|--------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------|
| Cockpit mostra "SSO Kerberos indisponível"                           | `PENGUARD_MOCK_MODE=true` ou Keycloak fora do ar                          | `docker compose logs api keycloak`; checar `.env`                                                          |
| Browser pede usuário/senha em vez de SPNEGO                          | Site não está na allowlist da Integrated Authentication                         | `edge://policy` → `AuthServerAllowlist`; ajustar GPO                                                       |
| Keycloak loga `Defective token detected` / `GSS-API`                  | SPN não bate, keytab desatualizado ou enctype não permitido                     | `klist -kte penguard.keytab`; comparar com `serverPrincipal`; reexecutar `ktpass`                    |
| `Clock skew too great`                                                | Relógio do Docker host ou DC desviado > 5 min                                   | Sincronizar via NTP em ambos os lados (`w32tm /resync` no DC)                                              |
| `KDC has no support for encryption type`                              | Keytab tem só AES256 e o cliente tenta AES128 (ou vice-versa)                   | Regerar keytab com `-crypto All`; alinhar `Set-ADUser -KerberosEncryptionType`                             |
| `Duplicate SPN found`                                                 | SPN registrado em outra conta                                                  | `setspn -Q HTTP/penguard.local`; `setspn -D ...` na conta errada                                     |
| Keycloak sobe mas Kerberos provider mostra "key tab file not readable"| Volume não montado ou permissões                                                | `docker compose exec keycloak ls -la /opt/keycloak/conf/penguard.keytab`                             |
| `Java security: no permission`                                        | Algoritmo legado desabilitado pelo Java                                         | Confirmar que `java-security-override.properties` está montado e o `JAVA_OPTS_APPEND` aponta para ele      |
| 302 em loop entre BFF e Keycloak                                      | `redirectUris` do client OAuth não inclui a URL chamada                         | Adicionar `PENGUARD_SSO_REDIRECT_URI` em `infra/keycloak/realm-penguard.json` e reimportar     |
| `state_mismatch` no audit                                             | Cookie de sessão `f_session` perdido (SameSite, hostname diferente)             | Garantir que o usuário acessa via `http://penguard.local:5173` (não `localhost`)                     |

Comandos úteis para diagnóstico:

```bash
# Ver o que o Keycloak carregou do keytab
docker compose exec keycloak bash -lc \
  'klist -kte /opt/keycloak/conf/penguard.keytab'

# Forçar nova obtenção de TGT no host Docker (debug)
docker compose exec keycloak kinit -V -k -t /opt/keycloak/conf/penguard.keytab \
  HTTP/penguard.local@PENGUARD.LOCAL

# Tail do audit no BFF
docker compose logs -f api | grep sso_kerberos
```

---

## 10. Checklist final antes de entregar

- [ ] Conta `svc-keycloak` criada no AD com senha forte e
      `PasswordNeverExpires=true`.
- [ ] `setspn -Q HTTP/penguard.local` retorna **apenas** `svc-keycloak`.
- [ ] `penguard.keytab` na raiz do repo, **não** commitado
      (`git status --ignored` confirma).
- [ ] DNS A + PTR para `penguard.local` apontando para o host Docker.
- [ ] `.env` aponta os valores browser-facing para `penguard.local:8080`
      e mantém `PENGUARD_KEYCLOAK_INTERNAL_BASE_URL=http://keycloak:8080`.
- [ ] `docker compose up -d --build` traz Keycloak saudável.
- [ ] `kvno HTTP/penguard.local@PENGUARD.LOCAL` retorna kvno > 0.
- [ ] Login na cockpit via SSO completa sem fallback para formulário.
- [ ] Audit registra `sso_kerberos / success` para um usuário do domínio.

---

## 11. O que **nunca** commitar

- `penguard.keytab` (já em `.gitignore`).
- `.env` com `PENGUARD_KEYCLOAK_CLIENT_SECRET` real.
- Hostnames internos da rede do cliente, IPs do DC produtivo, nomes de
  domínios reais.
- Senhas do `svc-keycloak`, do admin do Keycloak ou do realm.
- Dumps de log com headers SPNEGO (contêm material criptográfico).

Em caso de vazamento acidental: revogue a conta no AD, rode `ktpass`
novamente para invalidar o keytab antigo (a `kvno` muda) e gire o
`PENGUARD_KEYCLOAK_CLIENT_SECRET`.
