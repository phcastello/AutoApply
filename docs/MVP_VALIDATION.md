# Implementação e validação do MVP

Validação em 9 de outubro de 2026, Windows, Python 3.12. Base original: commit `053071ba1bba5733b522d78c3d645002d817e55a` do AutoApply 2.4.1. Implementação na branch `mvp-assisted` do fork `phcastello/AutoApply`. A publicação inclui código, documentação e fixtures explicitamente fictícias; dados privados e artefatos locais de validação ficam ignorados pelo Git.

## Diagnóstico confirmado no código

| Componente original | Evidência e decisão |
|---|---|
| Dashboard | Flask, blueprints, módulos JavaScript, CSS e navegação existentes reutilizados; aba assistida acrescentada como tela inicial. |
| Configuração/perfil | Pydantic e persistência JSON existentes expandidos com fatos estruturados confirmáveis e preferências opcionais. |
| SQLite | Tabelas applications, resume_versions, feed_events e Knowledge Base reutilizadas; duas tabelas auxiliares associam descrições/cache/proveniência. Migração aditiva. |
| Busca | LinkedIn/Indeed são scrapers Playwright, não APIs públicas garantidas. Preservados, sem autenticação real para validá-los. Greenhouse e Lever adicionados como consultas públicas somente leitura. |
| Matching | TF-IDF original funciona em testes e foi reutilizado para avaliar informações de todas as categorias e ordenar evidências. Acrescentadas regras de requisitos/preferências/tempo profissional. |
| Currículo | ReportLab original funciona, mas nomes/contatos/subtítulos longos podiam ultrapassar a largura. Corrigida quebra de linhas. Fluxo assistido monta texto exclusivamente de fatos confirmados. |
| Knowledge Base | Parser PDF/DOCX/TXT/MD e armazenamento funcionam em testes. Extração/ingestão antiga também pode incluir currículos gerados; esses registros não são fatos confirmados no novo fluxo. |
| IA | Chamadas HTTP reais para quatro provedores presentes no código. Aproveitadas para seleção de IDs; endpoint compatível configurável acrescentado. Respostas sem referências válidas falham. |
| Privacidade | API original devolvia chave; fallback podia gravá-la em texto puro. Corrigidos redaction, recusa de fallback inseguro e isolamento de chave por provedor/endpoint. Erros remotos não reproduzem corpos de resposta potencialmente sensíveis. |
| Execução | Instalação e servidor funcionaram no Windows. Corrigida configuração de origem do Socket.IO para a porta local efetiva. |
| Automação | Agendador e adaptadores preservados. Padrão novo é watch, agenda desativada; submissão não integra o fluxo assistido. Recursos antigos continuam experimentais. |
| Licença | MIT e copyright do autor preservados, sem modificações em LICENSE. |

## Testes automatizados

- Bateria focada em MVP/componentes reutilizados: **278 passaram**, um aviso de depreciação do PyPDF2, sem falhas.
- `tests/test_assisted_mvp.py`: **26 testes passaram**, incluindo perfil/preferências, normalização das duas fontes, deduplicação persistente, matching, seleção de fatos, datas profissionais sobrepostas, exclusão de fatos não confirmados, PDF/texto, DOCX, cache/versões/reabertura do SQLite, falhas de busca, URLs/encerramento/SSRF, importação, download, estados, redaction e isolamento de credenciais.
- `pip check`: sem dependências quebradas. Ruff nos módulos novos/alterados: passou. `git diff --check`: passou.
- Suíte histórica completa, módulos isolados: **1.415 passaram, 28 falharam e um módulo excedeu 60 segundos**. Não é apresentada como suíte completamente verde.
- Comparação em worktree intacta do upstream, mesmos Python/dependências e isolamento: **1.390 passaram, 27 falharam e o mesmo módulo excedeu 60 segundos**.

A diferença variável em analytics_enhanced vem de fixtures que reutilizam identificadores baseados em tempo, provocando UNIQUE constraint conforme velocidade da execução (13 falhas no baseline, 14 na última execução). Os demais grupos de falhas também estão no upstream: Workday/Ashby, classe abstrata de applier, paridade de traduções espanholas, expectativas históricas de KB/assembler e um teste de scraper. `test_bot_coverage` excede o limite em ambas as cópias.

Expectativas antigas sobre senioridade implícita, chave em texto puro, erros contendo corpo remoto e CORS foram atualizadas para os contratos deliberadamente corrigidos, mantendo testes funcionais de segurança e compatibilidade. Esses ajustes não escondem falhas dos módulos antigos.

Relatórios completos locais, ignorados pelo Git: `.validation/baseline-suite/report.json`, `.validation/final-suite-2/report.json` e arquivos `.log` por módulo. O runner retorna erro quando existem falhas/timeouts. O comando focado reproduzível está no README.

## Validação real

O teste utiliza dados profissionais **explicitamente fictícios** de `examples/profile-test.json`, inseridos pela própria interface em armazenamento isolado. Isso valida a aplicação sem fingir conhecer o histórico do usuário. As oportunidades e os links são reais, obtidos pela rede; nenhuma fixture substitui as APIs.

As consultas iniciais recuperaram 732 registros válidos da Stripe/Greenhouse e 206 da CI&T/Lever. O board Nubank consultado não retornou registros utilizáveis e não foi mantido como fonte padrão.

A última validação encontrou até cinco resultados:

| Vaga | Empresa/fonte | Compatibilidade | Link |
|---|---|---:|---|
| Master Data Developer, Brazil | CI&T / Lever | 53 | [Página específica](https://jobs.lever.co/ciandt/51618054-a487-4ffe-a60f-78392ad250d0/apply) |
| Master Data Developer (Amazon Neptune), Colombia | CI&T / Lever | 53 | [Página específica](https://jobs.lever.co/ciandt/b51b1a14-b9cd-4f45-b732-595936ed8a61/apply) |
| Forward Deployed Security Engineer | Stripe / Greenhouse | 49 | [Página específica](https://stripe.com/careers/listing/forward-deployed-security-engineer/8181003?gh_jid=8181003) |
| Abuse Research Engineer | Stripe / Greenhouse | 49 | [Página específica](https://stripe.com/careers/listing/abuse-research-engineer/8172503?gh_jid=8172503) |
| Data Developer (IA / Automação), Brazil | CI&T / Lever | 46 | [Página específica](https://jobs.lever.co/ciandt/36cdaaba-8821-4814-a763-cb0b68da881c/apply) |

HTTP 200, cargo e identificador foram confirmados nos cinco links nessa execução. Uma execução anterior marcou um deles como não verificado; o estado foi mostrado como tal. Os resultados podem mudar depois da data acima. Scores moderados não significam candidatos plenamente qualificados: as vagas Stripe exigem cinco/dez anos profissionais que o perfil acadêmico de teste não comprova, corretamente apresentados como possíveis eliminatórios.

Pelo navegador, o teste confirmou cadastro, salvamento, preferências, consulta, explicações/descrições, geração por vaga, visualização PDF, download PDF/DOCX e atualização manual de estado. O botão Abrir vaga foi clicado e abriu a URL específica da CI&T em uma nova aba. O backend foi encerrado e reiniciado com o mesmo diretório; perfil, vaga, currículo e estado continuaram disponíveis. Não houve erros JavaScript.

O PDF baixado tem uma página e 431 caracteres extraídos, com nome, e-mail, telefone, formação e projeto da fixture, sem qualificações externas acrescentadas. PDF renderizado com Poppler e DOCX com LibreOffice/`render_docx.py`; imagens finais inspecionadas, sem corte/sobreposição. O DOCX mantém coluna única, títulos pretos e não utiliza borda decorativa no título. Os arquivos de teste e imagens ficam em `.validation/live` e não são publicados no fork.

## O que não foi validado

- **IA real:** não foram fornecidas credenciais/modelo do usuário. Seleção e rejeição de IDs inventados foram testadas com mocks; há teste do provedor na interface para completar essa validação.
- **Perfil real:** nenhum histórico pessoal foi inferido da conta GitHub. O usuário precisa preencher/importar e confirmar suas informações.
- **Envio de candidatura:** nenhum envio foi realizado. O MVP prepara documentos e oferece a página específica para conclusão manual.
- **Scrapers/adaptadores antigos:** sem sessões LinkedIn/Indeed/ATS autenticadas, não é possível afirmar que funcionam de ponta a ponta. Permanecem experimentais.
- **Elegibilidade completa:** salário/país/idioma/contrato/jornada/visto podem exigir leitura manual. A ausência de metadado não satisfaz nem viola uma preferência automaticamente.
- **Tradução:** preferência altera títulos de seções; fatos mantêm idioma confirmado. Tradução profissional automática não está implementada.

## Continuidade

O fluxo P0 assistido foi executado pela interface. Histórico, importação, DOCX, deduplicação, cache e versões também estão presentes. Para automação futura, priorizar fontes ATS recorrentes, elegibilidade mais precisa, fila de revisão, limites e opt-in antes de reaproveitar os adaptadores de envio. Não implementar contorno de CAPTCHA ou autenticação.
