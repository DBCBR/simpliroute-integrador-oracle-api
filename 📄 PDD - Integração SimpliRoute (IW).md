# PDD - Integração SimpliRoute (IW) - Versão 2.1

## 1. Informações Preliminares e Objetivos

| Detalhe | Preenchido |
| :--- | :--- |
| **Nome do Processo** | Automação de Roteirização e Atualização de Status (SimpliRoute) |
| **Área de Negócio** | Logística / Operações |
| **Proprietário (Process Owner)** | **Valdecir Cabral Gaudard** |
| **Última Atualização** | **[Data Atual] (Webhooks e Configuração)** |
| **Versão** | **2.1 (Webhooks e Configuração)** |
| **Pontos Focais** | Gestor: **Valdecir Cabral Gaudard**; Técnico: **Simone Rocha**; Funcional: **Simone Rocha** |

### 1.1. Metas e Indicadores de Desempenho (KPIs)

| KPI (Foco) | Métrica / Fórmula | Valor Atual (As-Is) | Meta (To-Be) | Fonte |
| :--- | :--- | :--- | :--- | :--- |
| **Produtividade** | Tempo Médio de Criação da Rota (TME) | Não Mapeado | $< 5$ minutos | |
| **Recorrência** | Frequência de Verificação da Tabela de Eventos | N/A | **Temporal (A cada 1 hora)** | Confirmado |
| **Qualidade** | Taxa de Erro na Transferência de Dados | N/A | $< 1\%$ | |

---

## 2. Processo TO-BE (Como Será)

### 2.1. Fluxo Sistêmico de Transação (Atualizado: Webhook)

O fluxo será executado por um **Script em Python** com recorrência definida para verificar, enviar e atualizar os dados entre os sistemas. O mecanismo de **Consulta de Status (Seq. 5)** será alterado para **Webhook**, exigindo um servidor Web rodando em paralelo no contêiner.

| Seq. | Ação Principal | Plataforma | Referência Técnica |
| :--- | :--- | :--- | :--- |
| **1.** | Programação do Atendimento e Aprovação | IW | Equipes: Enfermagem, Médica ou Entrega. |
| **2.** | **Gatilho de Recorrência** | **Script Python** | Executa **polling** a **cada 1 hora** na API do Gnexum (Busca insumos e inicia o ciclo completo). |
| **3.** | Consulta de Insumos | Gnexum API | Expõe dados da tabela `TD_OTIMIZE_ALTSTAT`. |
| **4.** | Criação da Visita/Rota (**Envio**) | SimpliRoute API (**POST /routes/...**) | Envia **payload** JSON com dados mapeados do IW. |
| **5.** | **Recebimento de Status** | **Script Python (Serviço Web)** | **CRÍTICO:** Recebe o **Webhook Detalhado** do SimpliRoute. O Script precisa operar como um serviço web em paralelo para esta função. |
| **6.** | **Envio de Atualização de Status (SR -> Gnexum)** | Gnexum API (**POST**) | **Gera requisição para API do Gnexum com o status retornado do SimpliRoute.** |
| **7.** | Atualização da Tabela de Eventos | BD IW (TD\_OTIMIZE\_ALTSTAT) | O Gnexum atualiza o campo `ACAO` (Controle Interno) e recebe IDs. |
| **8.** | Notificação ao Portal da Família | Portal da Família API (POST) | Envia o **status** final (Rota `solarDeliveryStatus` / `solarSatisfactionSurvey`). |

#### 2.2. Dicionário de Dados e Mapeamento Completo

A Tabela do BD IW (`TD_OTIMIZE_ALTSTAT`) é o recurso central de insumo e produto.

| Campo BD IW | Tipo BD | Finalidade do Campo | Mapeamento (Destino na API) | Regras de Negócio e Uso |
| :--- | :--- | :--- | :--- | :--- |
| **`id`** | `long` | ID do registro automático. | Não mapeado. | Automático - não usado pela integração. |
| **`idreference`** | `long` | ID de referência da tabela. | Não mapeado. | No momento = null. |
| **`idadmission`** | `long` | ID de Atendimento do paciente. | **Portal Família:** `idAdmission`. | **Uso:** Em todas as chamadas para o Portal da Família. |
| **`idregistro`** | `long` | ID da Prescrição/Consulta. | **Portal Família:** `idPrescricao` (Entregas) ou `idConsulta` (Visitas). | **Regra:** Usado para criar o `title` da visita SimpliRoute. |
| **`tpregistro`** | `integer` | Tipo de Registro (1=VISITAS, 2=ENTREGAS). | **Campo de Lógica.** | Controla a lógica de mapeamento. |
| **`status`** | `integer` | Status da Visita/Entrega. | **Campo de Mapeamento.** | Mapeamento do `status` do SimpliRoute (`string`) para código numérico. |
| **`eventdate`** | `DATE` | Data completa do status. | **SimpliRoute:** `planned_date`. | **Regra:** Usado **apenas para ENTREGAS** (`tpregistro=2`). |
| **`hreventdate`** | `VARCHAR2(5)` | Somente Hora do Status. | **API Gnexum:** `horaProgramada`. | **Regra:** Usado **apenas para VISITAS** (`tpregistro=1`). |
| **`dteventdata`** | `VARCHAR2(10)` | Somente Data do Status. | **API Gnexum:** `dataProgramada`. | **Regra:** Usado **apenas para VISITAS** (`tpregistro=1`). |
| **`profissional`**| `VARCHAR2(60)` | Nome do Profissional. | **Campo de Lógica.** | A ser usado para identificar o tipo de atendimento (Médico/Enfermeira). |
| **`acao`** | `VARCHAR2(1)` | **Controle para integração.** | Não mapeado (Controle Interno). | 'A' = Aguardando Exportar. 'S' = Sucesso. |
| **`retorno`** | `VARCHAR2` | Campo de Retorno da Automação. | Não mapeado. | Receberá o ID da Visita (`id`) e ID da Rota (`route_id`). |
| **Endereço Completo** | `VARCHAR2(100)` | Endereço formatado para geolocalização. | **SimpliRoute: `address`**. | **CRÍTICO:** O Gnexum API deve buscar o campo `ENDERECO_GEOLOCALIZACAO` de tabelas relacionadas (Paciente/Atendimento). |
| **... [Título]** | *A Definir* | Nome da Visita (ID de referência). | **PENDÊNCIA CRÍTICA: SimpliRoute: `title`**. | **Obrigatório.** Necessário definir a concatenação (ex: ID do paciente + ID do registro). |
| **... [Tempo/Duração]** | *A Definir* | Tempo estimado de serviço/atendimento. | **SimpliRoute: `duration`**. | **CRÍTICO para VISITAS (tpregistro=1)**. **FONTE:** Será puxada de uma tabela atualizada pelo Gnexum. |
| **Volume/Carga (Entregas)** | `NUMBER` | Volume total dos itens. | **SimpliRoute: `load`**. | **CRÍTICO:** O Gnexum API deve buscar o campo `VOLUME` da tabela **TD\_OTIMIZE\_ITENS**. Usar **0** para Visitas. |
| **... [Detalhe Itens]**| *A Definir* | Lista de produtos/materiais por visita/entrega. | **SimpliRoute: `items` (Array)**. | **CRÍTICO:** O Script Python deve consultar a tabela **TD\_OTIMIZE\_ITENS** e construir o array JSON. |
| **... [Detalhe Profissional]**| *A Definir* | Código da Categoria/Profissão. | **PENDÊNCIA CRÍTICA: SimpliRoute: `...`**. | **NÃO USARÁ `skills_required`**. Aguardando qual campo do SR será usado para filtrar a Visita (Médico/Enfermeira). |

#### 2.3. Endpoints Utilizados SimpliRoute

| Ação | Endpoint | Descrição | Parâmetros de Query |
| :--- | :--- | :--- | :--- |
| **POST** | `/v1/routes/visits/` (ou outro) | Criação e otimização de uma nova rota (Contém a lista de visitas/itens). | N/A (Payload JSON) |
| **Webhook POST**| `/SUA-URL-PUBLICA/` | **Recebimento de Webhook Detalhado** (Notificação de Status). | Payload JSON enviado pela SR. |

---

## 3. Requisitos Técnicos e Próximos Passos

### 3.2. Solicitações para Avanço (Ações Imediatas)

| Recurso | Item Solicitado | Status | Observações |
| :--- | :--- | :--- | :--- |
| SimpliRoute API (Criação) | **Endpoint de Envio (POST).** | **PENDENTE** | **CRÍTICO:** Aguardando definição se será `/v1/routes/visits/` ou outra rota. |
| SimpliRoute Config. | **Mapeamento de Profissionais.** | **PENDENTE** | **CRÍTICO:** As Habilidades (`skills_required`) **NÃO** serão usadas. Aguardando a equipe do SR definir qual campo será usado para incluir a informação "Médico/Enfermeira". |
| Mapeamento Funcional | **Definição do campo Título (`title`).** | **PENDENTE** | **CRÍTICO:** O cliente precisa definir a regra de concatenação (ex: ID do paciente + ID do registro) para o `title`. |
| Gnexum API | **Endpoints de Leitura e Escrita/Atualização.** | **PENDENTE** | **CRÍTICO:** Necessário confirmar a URL de Leitura (`GET` da `TD_OTIMIZE_ALTSTAT`) e o Endpoint de Escrita/Atualização. |
| SimpliRoute | Confirmação de ambiente de Homologação. | **PENDENTE** | Verificação em curso (se usará Homologação ou Produção). |
| **Ação Técnica** | **Implementação do Servidor Web.** | **PENDENTE** | **CRÍTICO:** Devido ao Webhook, o Script Python deve ser reestruturado para ser um **serviço web** que ouve em uma porta. |

#### 3.3. Aprovações (Sign-off)

| Função | Nome | Assinatura | Data de Aprovação |
| :--- | :--- | :--- | :--- |
| Process Owner (Gestor do Projeto) | Valdecir Cabral Gaudard | | |
| Analista de Negócios (BA) | [David Barcellos Cardoso] | | |
| Arquiteto de Soluções | [David Barcellos Cardoso] | | |
