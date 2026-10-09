# AI Job Application Assistant

MVP local para descobrir vagas publicadas, comparar com um perfil confirmado e baixar um currículo por oportunidade. A candidatura é concluída manualmente na página oficial. O fluxo principal está na aba **Candidaturas assistidas**, em português brasileiro.

Baseado no [AutoApply de Abhishek Mandapmalvi](https://github.com/AbhishekMandapmalvi/AutoApply), versão 2.4.1, commit `053071ba1bba5733b522d78c3d645002d817e55a`. Reutiliza Flask, dashboard, SQLite, Knowledge Base, parser PDF/DOCX/TXT/MD, TF-IDF, ReportLab e provedores de IA. A [licença MIT e copyright original](LICENSE) permanecem intactos. A [documentação original arquivada](docs/UPSTREAM_README.md) não comprova o funcionamento das integrações históricas.

Fork: [phcastello/AutoApply](https://github.com/phcastello/AutoApply). Código do MVP na branch [mvp-assisted](https://github.com/phcastello/AutoApply/tree/mvp-assisted).

## Instalação e execução no Windows

Requisitos: Python 3.11+, Git e internet para consultar vagas. Validado com Python 3.12 no Windows. Node, Docker, PostgreSQL, Redis, LaTeX e login LinkedIn não são necessários para o fluxo assistido.

No PowerShell, dentro da pasta do projeto:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe run.py --no-browser
```

Abra **http://localhost:5000** no navegador. Caso a porta esteja ocupada, o terminal informa a porta efetiva entre 5000 e 5010. Mantenha o terminal aberto; Ctrl+C encerra. Janela nativa opcional: `.\.venv\Scripts\python.exe run.py --gui`, com WebView2 instalado.

O servidor escuta em `127.0.0.1`. Não o publique na internet: o dashboard dá acesso aos seus documentos locais. Dados padrão em `%USERPROFILE%\.autoapply`. Para separar perfis/testes, defina `$env:AUTOAPPLY_DATA_DIR = "$PWD\.validation\meu-teste"` antes de iniciar. Cada diretório representa um perfil, sem sincronização ou autenticação multiusuário.

## Perfil e importação

1. Abra **Candidaturas assistidas** e preencha nome, e-mail e contatos desejados.
2. **Adicionar informação** permite registrar experiência, formação, projeto, competência, idioma, certificação, pesquisa e outras informações.
3. Use uma informação por entrada. Preencha empresa/instituição, cargo/curso/projeto, datas, tecnologias confirmadas, link, modalidade e proficiência quando disponíveis.
4. Marque **Revisei e confirmo esta informação** após conferir. Salve o perfil.

Projetos acadêmicos, iniciação científica, monitoria, publicações e atividades adicionais podem ser registrados em Pesquisa ou Outras informações. Para comparar duração profissional, use datas **AAAA-MM**; datas livres permanecem no currículo e exigem conferência no matching. O link GitHub é apenas contato; não inferimos competências de repositórios.

**Importar PDF, DOCX, MD ou TXT** extrai texto localmente em rascunhos, sem enviar o documento para IA. Revise, divida, categorize e confirme. Limite: 5 MB. PDFs digitalizados precisam de OCR externo.

**Trazer sugestões da Knowledge Base** reaproveita entradas antigas como rascunhos não confirmados. A KB original pode conter texto extraído por IA ou de currículos antigos: confira a origem. O novo fluxo nunca usa automaticamente esses textos ou currículos gerados como fatos.

O perfil persiste em `config.json` no diretório privado de dados. Cada currículo registra os fatos utilizados e seus IDs em `provenance.json`.

## Preferências e vagas reais

Configure cargos, áreas, palavras-chave/exclusões, senioridade, localização, países, modalidades, horas, jornada, salário, contratos, idiomas, realocação, visto, empresas bloqueadas, idioma do currículo e pontuação mínima. Campos vazios não restringem a busca.

As fontes comprovadamente operacionais são as APIs públicas de [Greenhouse](https://docs.greenhouse.io/job-board.html) e [Lever](https://github.com/lever/postings-api), usadas somente para leitura. Configure boards de empresas, por exemplo **stripe** no Greenhouse e **ciandt** no Lever. Não é uma busca global por todas as empresas. Obtenha o board token na página oficial da empresa; não use identificadores de empresas por suposição.

- Cargos são alternativas e usam texto do título sem distinguir maiúsculas. Palavras incluídas são alternativas na descrição/título.
- Palavras excluídas e empresas bloqueadas excluem resultados novos. A pontuação mínima filtra a exibição preservando histórico.
- Limite padrão: 20 vagas por busca, configurável de 1 a 100. Até 12 boards por consulta.
- País, salário/moeda/período, contrato, jornada, idioma e horas podem exigir revisão manual quando faltam dados comparáveis. Valores ausentes não são declarados incompatíveis.
- Áreas e realocação persistem como contexto e ainda não alteram a pontuação automaticamente.

Clique em **Salvar e pesquisar vagas reais**. Falhas das fontes aparecem mesmo quando outra fonte funciona. Zero resultados significa zero, sem dados demonstrativos.

As vagas apresentam descrição completa, requisitos explicitamente identificados, fonte, URL original/candidatura, descoberta e publicação quando disponível. `updated_at` não é tratado como publicação. Modalidade e senioridade só são informadas quando identificáveis.

Até cinco links por consulta são conferidos por HTTP, redirecionamentos, identificador e cargo. **Link não verificado** indica que essa correspondência não foi comprovada. **Verificar link** repete a conferência. Vagas identificadas como encerradas ficam ocultas. **Abrir vaga** leva à oportunidade específica.

## Matching

Utiliza evidências confirmadas de todas as categorias, tecnologias, TF-IDF original e regras de preferências. Requisitos obrigatórios explícitos têm peso maior que diferenciais. Exibe score 0–100, correspondências, lacunas, possíveis eliminatórios, conferências pendentes e recomendação.

Tempo profissional une períodos sobrepostos de experiências confirmadas; formação e projetos não contam como tempo profissional. Exigências de anos sem comprovação são marcadas como possíveis eliminatórios. O cálculo não prova que cada período atende à especialidade exigida: confira a descrição. Seções não identificadas pelo parser são apresentadas como desconhecidas.

O score não é chance de contratação ou aprovação ATS. Desconhecer um diferencial não provoca descarte automático. O matching do MVP é local; IA é opcional para seleção de fatos no currículo.

## Configuração de IA e privacidade

Na seção **IA opcional e privacidade**, escolha OpenAI, Anthropic, Google ou DeepSeek, informe modelo e chave, salve e use **Salvar e testar provedor**. Os modelos padrão são herdados do upstream e podem não estar disponíveis na sua conta; informe um modelo válido para seu provedor.

Para servidor compatível com Chat Completions, informe endpoint **completo**, por exemplo `http://127.0.0.1:1234/v1/chat/completions`, e modelo. HTTP só é permitido para localhost; endpoints remotos precisam de HTTPS. Modelos locais podem dispensar chave.

**Usar IA para selecionar informações** transmite os textos profissionais candidatos e a descrição ao provedor. Contatos do cabeçalho não compõem o pedido; evite dados sensíveis desnecessários no texto das experiências. A resposta só seleciona IDs existentes. Não reescreve qualificações, cargos, datas ou resultados. Respostas inválidas provocam erro, sem publicar currículo.

Chaves ficam no cofre do sistema por provedor/endpoint e não são devolvidas pela API de configuração. Sem cofre, o aplicativo recusa gravar chave em texto puro. Alternativa por sessão:

```powershell
$env:AUTOAPPLY_LLM_API_KEY = "sua-chave"
.\.venv\Scripts\python.exe run.py --no-browser
```

Essa variável vale para o provedor escolhido na sessão: não use chave de um serviço em outro endpoint. `.env.example` documenta opções; `.env` **não é carregado automaticamente**. Não versione chaves, documentos pessoais, sessões ou diretórios de dados.

## Currículos, download e histórico

Clique em **Gerar currículo** na vaga. O programa seleciona/ordena fatos relevantes confirmados e mantém contatos corretos. PDF tem texto selecionável e DOCX é editável. A preferência de idioma altera **títulos das seções**; os fatos preservam o idioma confirmado. Para texto inteiramente traduzido, confirme versões corretas no perfil. Tradução livre por IA não está implementada.

PDFs são reabertos e verificados quanto a integridade, texto, nome/contatos, fatos selecionados, placeholders e páginas antes do download. A interface informa falhas. Use **Visualizar PDF**, **Baixar PDF**, **Baixar DOCX** e **Fontes das afirmações**. Não há garantia universal de aprovação ATS.

Arquivos por geração: `<dados>/outputs/<empresa>/<id interno>/<data-versão>/`, com `resume.pdf`, `resume.docx`, `resume.md`, `provenance.json`, `job_description.txt` e `match_analysis.json`.

Perfil, descrição, idioma e configuração de seleção compõem o cache. Uma versão idêntica válida é reaproveitada; **Gerar nova versão** força outra. Deduplicação usa ID/fonte, URL canônica e empresa/cargo/localização. O último critério pode unir posições distintas com metadados iguais; confira quando a empresa publica múltiplas requisições semelhantes.

Estados manuais: Descoberta, Não tenho interesse, Quero me candidatar, Currículo preparado, Candidatura realizada, Resposta recebida, Entrevista, Rejeitada e Contratado. Estados, vagas, documentos, versões e falhas persistem no SQLite existente, inclusive após reiniciar. Buscas não sobrescrevem o estado manual.

## Testes

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest tests/test_assisted_mvp.py tests/test_settings.py tests/test_quick_wins.py tests/test_ai_engine.py tests/test_resume_renderer.py tests/test_database.py tests/test_document_parser.py tests/test_resume_scorer.py tests/test_filter.py tests/test_coverage_boost.py -q
```

Essa seleção cobre o MVP e módulos reutilizados. A suíte histórica completa tem falhas anteriores ao fork e um teste do bot que pode bloquear. Execute módulos isolados, com limite de 60 segundos e relatório:

```powershell
.\.venv\Scripts\python.exe scripts/run_test_modules.py --output .validation/suite
```

O runner retorna código diferente de zero se qualquer módulo falhar/exceder o limite. Resultados e diagnóstico em [docs/MVP_VALIDATION.md](docs/MVP_VALIDATION.md).

Validação real reproduzível com perfil **explicitamente fictício**, sem candidatura enviada:

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe scripts/validate_live.py
```

O script usa a interface para preencher perfil/preferências, consultar APIs reais, encontrar até cinco vagas, gerar/baixar PDF/DOCX e visualizar PDF. Reinicia o backend e confere persistência. Nenhuma fonte real é substituída por fixture; indisponibilidade faz o teste falhar. Relatório em `.validation/live`, ignorado pelo Git. O perfil fictício de referência está em `examples/profile-test.json`; nunca é carregado na aplicação normal.

## Limitações e evolução

Scrapers LinkedIn/Indeed, adaptadores e agendador originais foram preservados, mas não validados com suas sessões. Novas configurações usam `watch` e agenda desativada. Configurações antigas que já habilitaram automação não são alteradas silenciosamente: revise-as antes de iniciar uma base existente.

Sem novo envio automático, tradução livre, OCR, importação de projetos GitHub, acompanhamento de e-mail ou carta de apresentação no fluxo assistido. Algumas telas antigas continuam em inglês. Metadados ausentes precisam de revisão manual. Requisitos são extraídos por heurística, não por análise jurídica de elegibilidade.

Próxima evolução: agendar descoberta ATS, melhorar requisitos objetivos e conectar uma fila revisável aos adaptadores, com opt-in explícito, limites diários e encaminhamento manual em bloqueios. Vinte envios/dia continuam planejados. CAPTCHA/autenticação obrigatória não são contornados.

## Branch do MVP e publicação de alterações

O MVP está na branch `mvp-assisted` do fork. Para obter essa implementação:

```powershell
git clone --branch mvp-assisted https://github.com/phcastello/AutoApply.git
cd AutoApply
```

Nesta cópia de desenvolvimento, `upstream` aponta ao autor e `origin` a `phcastello/AutoApply`. Para publicar alterações futuras, confira `git status --short` antes de criar o commit. Ambientes, `.validation`, outputs e credenciais estão ignorados.

```powershell
git add .
git commit -m "Implement assisted job discovery and confirmed-profile resumes"
git push -u origin mvp-assisted
```

Para outra conta, crie um fork pelo botão Fork do original e altere `origin`. Preserve a licença MIT.
