# Correção da importação de perfil

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
