# Integração de IA: incidente e verificação

Verificado em 15/10/2026, checkout `AutoApply_fork`, branch `mvp-assisted`, base `52c0ac0`.
O caminho antigo informado, `ApplicationAIssistant`, não existia neste ambiente. Nenhum clone, reset, commit ou publicação foi feito.

## Causa confirmada

Foi reproduzido um pedido equivalente ao validador antigo com a credencial já configurada no backend, o modelo **gpt-6.1-sol**, Chat Completions e `max_tokens: 8192`.
A OpenAI respondeu **HTTP 400**, código **unsupported_parameter**, parâmetro **max_tokens**.
O corpo bruto e a credencial não foram exibidos nem registrados. A resposta confirma incompatibilidade do request; não indica chave inválida.

O código antigo capturava qualquer exceção em `validate_api_key`, retornava apenas `False` e a interface mostrava “Invalid API key or provider error”. `_raise_api_error` descartava código e parâmetro. O teste antigo tinha timeout por tentativa de 15 segundos; o fluxo novo possuía outra implementação de endpoint personalizado e também usava `max_tokens` indiscriminadamente.

Após a correção, **um único teste real** com a mesma credencial, **gpt-6.1-sol**, **Responses**, `max_output_tokens: 4096`, `reasoning.effort: low` e prazo total de 60 segundos concluiu a geração. Não foi necessário alterar o perfil, endpoint salvo, modelo salvo ou credencial do usuário. Houve duas chamadas reais nesta investigação: reprodução e verificação.

## Implementação

- `config/ai_destination.py`: normalização de URL-base e endpoint completo, protocolo e destino das credenciais.
- `core/ai_configuration.py`: resolução da configuração ainda não salva, preservação de chave vazia e metadados públicos iguais nas duas telas.
- `core/ai_engine.py`: transporte e extração por protocolo usados por teste, importação, seleção e geração via `invoke_llm`. OpenAI oficial usa Responses por padrão. Endpoints antigos explícitos de Chat Completions permanecem nesse protocolo; OpenAI oficial recebe `max_completion_tokens`. DeepSeek e servidores compatíveis mantêm `max_tokens` em Chat Completions. Anthropic e Google preservam seus contratos próprios.
- Testes de geração fazem uma chamada sem perfil, sem tentativas pagas automáticas, sem temperatura, modalidade premium ou substituição de modelo. Modelos novos podem ser digitados livremente.
- Respostas incompletas, vazias ou recusadas são falhas. Somente erros curados, código/parâmetro reconhecidos e identificador de request são devolvidos; corpos remotos podem conter segredos e nunca são repassados.
- Credenciais ficam no cofre do sistema, vinculadas ao provedor e URL-base. Slots anteriores são lidos durante a migração. Campo vazio conserva a chave; máscaras são recusadas. Remoção é uma ação explícita. Redirecionamentos de requests autenticados não são seguidos.
- `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY` e `DEEPSEEK_API_KEY` são aceitas apenas no destino oficial correspondente. Para `AUTOAPPLY_LLM_API_KEY`, configure também `AUTOAPPLY_LLM_PROVIDER`; para um servidor personalizado, configure `AUTOAPPLY_LLM_ENDPOINT` com a mesma URL-base/endpoint. A variável genérica sem escopo não é enviada a destinos arbitrários. Chaves de ambiente não são copiadas ao JSON ou frontend.

## Hipóteses não confirmadas para o incidente

Não foi demonstrado erro de autenticação, acesso ao projeto, inexistência do modelo, falta de saldo ou indisponibilidade da conta. Essas condições têm diagnósticos próprios e não devem ser confundidas com a causa reproduzida. Uma resposta bem-sucedida comprova acesso naquele momento, não disponibilidade permanente ou acesso de outras contas.

## Fontes oficiais consultadas

- [GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol): Responses e Chat Completions; esforços low, medium, high, xhigh e max; none e minimal não suportados.
- [Migração para Responses](https://developers.openai.com/api/docs/guides/migrate-to-responses): `input`, saída tipada em `output`, `text.format` e `store: false`.
- [Responses: criar resposta](https://developers.openai.com/api/reference/resources/responses/methods/create): `max_output_tokens` inclui raciocínio e texto.
- [Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create): `max_completion_tokens` e depreciação de `max_tokens`.

## Testes reproduzíveis sem segredos

Execute `.venv\Scripts\python.exe -m pytest tests/test_ai_integration.py tests/test_ai_engine.py tests/test_assisted_mvp.py tests/test_config_api.py tests/test_settings.py -q`.
Os testes usam credenciais fictícias, destinos controlados e diretórios temporários; cobrem envelopes, isolamento, parâmetros, erros HTTP, resposta vazia/incompleta, timeout total e paridade entre `/api/ai/validate` e `/api/assistant/ai/test`.

## Resultado desta rodada

365 testes passaram na seleção de regressão: IA, cofre e migração, perfil, preferências geográficas, APIs, telas, analytics, importadores e renderizador. Inclui o fluxo completo em Chromium: testar com perfil vazio sem salvar, salvar a chave no cofre fictício, importar e confirmar perfil, escolher modalidades/cidade, buscar uma fonte controlada, gerar currículo, visualizar e baixar PDF. Capturas desktop e celular foram inspecionadas; navegação e sobreposição do botão de salvar foram corrigidas. Lint dos arquivos Python alterados, sintaxe dos JavaScript e `git diff --check` passaram.

Uma consulta pública real ao Lever/CI&T retornou 205 vagas com descrição e URL específica. Uma checagem de leitura no aplicativo real confirmou provedor restaurado, chave ausente do campo da interface, quatro áreas e ausência de erros JavaScript.

A suíte global **não está verde**. Foram observadas falhas nos testes antigos de Workday/Ashby (método `_upload_resume` ausente e expectativa divergente de tentativas de upload), uma divergência antiga no retorno da deduplicação de cargos da KB e travamento nos testes do loop do bot. Os registros de baseline já existentes no checkout também apontam falhas nesses módulos e timeout em `test_bot_coverage`. Esses aplicadores e o banco não foram alterados nesta rodada. Não houve candidatura enviada, commit, push ou PR.

Dois problemas dos próprios testes foram corrigidos para permitir a regressão: IDs de analytics dependiam da resolução do relógio, e o worker de shutdown podia sobreviver ao mock de `os.kill`. Expectativas de UI e de nomes do cofre foram atualizadas para os contratos novos. A remoção de uma chave grava a versão de credenciais para impedir que um slot legado a restaure depois.

A interface identifica os modos atuais: seleção local ou seleção de fatos por IA, ambos preservando o texto confirmado. A importação inteligente extrai sugestões com trechos de origem; a geração assistida não implementa reescrita ou tradução livre. A preferência de idioma é identificada como idioma dos títulos das seções.
