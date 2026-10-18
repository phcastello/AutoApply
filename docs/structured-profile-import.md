# Correção da importação de perfil

## Atualização: atuações por cliente ou projeto

O reconhecimento de `Atuação com <cliente>:` e `Atuação para <cliente>:` agora produz atividades estruturadas dentro da empresa prestadora. Subtítulos aninhados e subtítulos explicitamente chamados de atuação recebem o mesmo agrupamento. O cliente autorizado de um vínculo que informa uma data própria de atuação também recebe uma atividade. Essas datas não alteram o período do vínculo nem o cálculo de experiência, que continua unindo somente os períodos das empresas.

O teste contra o parser anterior confirmou a perda: o fixture fictício tinha dois vínculos, mas somente uma atividade (a PoC); as duas atuações nomeadas estavam em `date_notes`, e o cliente da segunda empresa não tinha atividade. A extração corrigida mantém dois vínculos e quatro atividades (três e uma), com aproximações, tecnologias, autoria individual e contexto não comercial da PoC preservados. A versão do mecanismo de importação passa a 3; o esquema de armazenamento das atividades permanece compatível.

Na revisão e no perfil salvo, **Atuações por cliente ou projeto** permite adicionar, editar título/descrição/período/tecnologias e excluir atividades. A empresa contratual é identificada explicitamente. Editar atividades no perfil pede nova confirmação do vínculo; editar ou cancelar uma proposta de importação não altera a confirmação já existente. Textos longos e datas aproximadas podem ser revisados sem truncamento em campos de múltiplas linhas.

A reimportação retorna `updates` separadamente de novas `entries`. Cada proposta contém `target_id`, `before`, `proposed`, `incoming` e a quantidade de atividades novas. A identidade usa empresa/cargo/início; para o mesmo documento, uma correção manual do cargo também é preservada. Cargos ou períodos distintos não são unidos por similaridade. A revisão mostra antes/depois e exige marcar **Atualizar este vínculo existente (preservar ID)**. Campos e atividades anteriores são mantidos, inclusive a PoC cujo título era encurtado pelo mecanismo anterior; somente atividades ausentes são acrescentadas. A escolha de aplicar como rascunho ou confirmar é explícita, e a persistência salva backup do perfil anterior, sem credenciais. O histórico de currículos e os IDs existentes não são reescritos.

Matching local e seleção por IA consideram títulos, descrições e tecnologias das atividades. A seleção por IA continua escolhendo IDs dos vínculos, com atividades públicas subordinadas. Na montagem de PDF/DOCX, as atividades com relevância textual para a vaga são selecionadas dentro do mesmo vínculo; se a vaga não fornece vocabulário suficiente para diferenciá-las, o grupo é preservado. A seleção não modifica o perfil salvo. Observações de datas, trechos de origem e instruções internas ficam fora do conteúdo profissional e do prompt de seleção. O contexto factual de uma PoC sem contrato permanece público, sem se transformar em alegação de implantação comercial.

Validação: 161 testes de regressão passaram, cobrindo importação, Markdown/PDF/DOCX/TXT, matching, seleção por IA simulada, geração e extração de PDF/DOCX, proveniência, edição no navegador, reimportação explícita, preservação de confirmação, backup, deduplicação, períodos simultâneos e cálculo de experiência. O fixture adicional `tests/fixtures/client_activities.md` é inteiramente fictício. Ruff e a verificação de whitespace também foram executados.

O documento real foi validado no Chromium de teste, em diretório privado isolado: dois vínculos, atividades agrupadas em três e uma, atualização desmarcada por padrão, cancelamento sem alteração, mesmos IDs, persistência após reinício e 17 fatos ignorados como duplicatas na reimportação seguinte. Nenhum erro de JavaScript. Documento, extrações, capturas e backups ficaram em `.validation/client-real-verified/`, ignorado pelo Git. O perfil de uso normal não foi substituído automaticamente; a atualização fica disponível para revisão. Nenhum commit ou push foi feito.

Verificação em 18/10/2026 no checkout existente, branch `mvp-assisted`. Alterações locais anteriores foram preservadas; nenhum commit, push ou PR foi feito.

## Reprodução e causa confirmada

O documento fornecido foi localizado em Downloads. O importador e a interface anteriores foram guardados apenas em `.validation/import-before` e executados em servidor de teste com o arquivo original. No navegador, os rótulos de nome e telefone apareceram dentro de fatos profissionais e o campo de nome continuou vazio.

No caminho básico anterior, a reprodução produziu 7 entradas de outras informações, 4 de experiência, 15 de formação e 3 de idiomas, sem reconhecer projetos. Isso confirma a classificação incorreta e o vazamento de contatos para fatos; não comprova que a tentativa original do usuário executou exatamente esse caminho. O perfil original disponível neste ambiente não contém registros importados e o código anterior não persistia o modo executado.

As causas no código eram concretas: aliases de seção restritos a igualdade exata, descarte da hierarquia de subtítulos, tratamento de parágrafos e campos como texto indistinto, ausência de esquema de contatos na IA e aplicação imediata dos rascunhos na lista profissional. O modo básico vinha de uma caixa de IA desmarcada por padrão. Não foi encontrado fallback automático de erro de IA para o básico; por isso nenhuma falha do provedor foi presumida.

## Fluxo corrigido

- **Básico:** extrai somente texto para consulta. Não cria fatos nem preenche campos e não é anunciado como extração estruturada.
- **Estruturado local:** usa títulos, subtítulos, campos nomeados e tabelas de contato. DOCX preserva níveis de títulos e ordem de tabelas; PDF, TXT e Markdown passam pelo mesmo esquema. Documentos sem texto recebem erro explícito; não foi acrescentado OCR.
- **Inteligente com IA quando necessária:** tenta a estrutura explícita primeiro, informa quando a IA não foi necessária e exige consentimento para enviar texto ao provedor. A IA recebe JSON Schema; a aplicação também valida tipos, trechos de origem, campos factuais, contatos, datas e restrições. Os adaptadores usam os envelopes próprios de Responses e Chat Completions. Falhas retornam diagnóstico seguro sem aplicar um fallback bruto.
- **Revisão:** contatos, vínculos, atividades, formação, projetos, competências, idiomas e restrições são apresentados antes de aplicar. Campos existentes diferentes só são substituídos por seleção explícita. É possível cancelar, editar, excluir, confirmar individualmente ou confirmar o lote revisado. Rascunhos antigos não confirmados do mesmo arquivo podem ser substituídos somente se selecionados.
- **Persistência e identidade:** fatos importados recebem identidade estável por conteúdo factual, com provedor de extração/mecanismo, modo e versão registrados. A deduplicação funciona contra registros salvos e rascunhos ainda não salvos. Não utiliza similaridade para unir cargos ou períodos diferentes. Correções existentes são preservadas na reimportação.

## Precisão e confidencialidade

Atividades internas ficam dentro do vínculo da empresa; clientes e prospecções não são promovidos a empregadores. Vínculos simultâneos continuam distintos e o cálculo existente de meses une períodos sobrepostos.

Datas precisas podem ser normalizadas para ano/mês; previsões e aproximações permanecem explícitas. A conclusão das obrigações acadêmicas e a previsão de diplomação são preservadas separadamente. Idiomas mantêm nível e origem da avaliação; não são criadas certificações por inferência.

Restrições e notas de confidencialidade ficam em `generation_constraints`, fora do texto de currículo. Trechos de origem não são enviados à seleção por IA. A geração usa fatos públicos confirmados e inclui atividades do vínculo no mesmo grupo. Localização marcada como referência não vira residência no cabeçalho nem elegibilidade remota confirmada. Texto bruto legado com contatos ou instruções misturadas é bloqueado na geração até revisão.

Antes da primeira aplicação de novos fatos importados, é salvo um backup privado do perfil anterior em `<dados>/backups/profile-before-import-*.json`. O backup não contém a configuração de credenciais.

## Resultado e validação

O arquivo real foi importado pelo navegador em diretório de dados privado e ignorado pelo Git. Foram conferidos 11 campos de contato, 2 vínculos profissionais, 1 atividade interna de PoC, 1 formação, 7 projetos, 4 grupos de competências e 3 idiomas, todos os 17 fatos inicialmente pendentes. Foram preservadas 22 restrições/observações, fora do conteúdo profissional.

O processo Python foi encerrado e iniciado novamente, e os campos e rascunhos continuaram salvos. Uma nova importação ignorou os 17 fatos já cadastrados. Capturas da revisão e dos campos preenchidos foram inspecionadas; não houve erro de JavaScript. Para esse Markdown, a estrutura local foi suficiente: o resultado registrou `ai_used: false`, sem envio ao provedor.

384 testes da seleção de regressão passaram. Outros 34 testes focados passaram após a inclusão da auditoria de importação. A seleção cobre parser, Markdown/PDF/DOCX/TXT, contatos, períodos simultâneos, atividades internas, previsões, idiomas autoavaliados, restrições, backup, deduplicação, edição/exclusão/cancelamento/confirmação na revisão, falha de IA sem fallback e envelopes de JSON Schema nos dois protocolos. A suíte global do repositório possui falhas históricas já documentadas; não é declarada inteiramente verde.

O fixture versionado em `tests/fixtures/structured_career.md` usa nomes, empresas, contatos, projetos e URLs fictícios. O documento real, os contatos extraídos, capturas, backups e os scripts de verificação real ficam somente em `.validation/`, ignorado pelo Git.

O `.venv` existente apontava para um Python removido. Para a validação foi usado o Python 3.12 já instalado com LibreOffice e as dependências existentes do projeto via `PYTHONPATH`; não houve instalação nem substituição do ambiente antigo. Os testes usaram `--basetemp` dentro de `.validation` devido às permissões do ambiente.

## Referência do contrato de IA

[Documentação oficial de saídas estruturadas](https://developers.openai.com/api/docs/guides/structured-outputs): JSON válido não implica aderência a um esquema; Responses usa `text.format` e Chat Completions usa `response_format`. A implementação mantém também validação local e revisão humana, que são necessárias para avaliar os fatos e os campos efetivamente preenchidos.
