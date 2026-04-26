# 🤖 Diretrizes do Agente Frontend (Antigravity)
**Projeto:** FortiDashboard (NG-SOC Frontend)
**Objetivo:** Desenvolver uma interface modular, "plug and play", com um layout livre (estilo Power BI/Photoshop) onde widgets são instanciados via chat com IA.

## 🛠️ Stack Tecnológica Exigida
Você DEVE utilizar estritamente as seguintes tecnologias. Não sugira alternativas fora desta lista sem autorização prévia:
* **Core:** Vue 3 (utilizando APENAS a Composition API com `<script setup>`).
* **Gerenciamento de Estado:** Pinia (fonte única de verdade para coordenadas X/Y e Z-index dos widgets).
* **Estilização:** Tailwind CSS (uso de classes utilitárias diretamente nos componentes).
* **Física e Animação:** Motion for Vue (para drag and drop livre, transições suaves e layout espacial).
* **Gráficos:** [A definir: Chart.js ou ECharts] envelopados em componentes Vue.
* **Ícones:** Lucide Vue.

## 📐 Regras de Arquitetura (O "Canvas")
1.  **Lógica Espacial:** Trate o dashboard central como um plano cartesiano. Cada "Widget" é um objeto independente que possui propriedades de posição `(x, y)`, tamanho `(width, height)` e camada `(z-index)` armazenadas no Pinia.
2.  **Componentes Dinâmicos:** O renderizador principal deve ler a store do Pinia e iterar sobre um array de `activeWidgets`, usando a tag `<component :is="...">` do Vue para instanciar gráficos dinamicamente.
3.  **Isolamento:** Componentes de visualização (os gráficos em si) não devem saber sua própria posição. Eles devem ser "filhos" de um `<DraggableContainer>` genérico que lida com o *Motion for Vue*.

---

## 🚀 Fases de Desenvolvimento (Sprints)

### Fase 1: Fundação e Layout Base
* **Setup Inicial:** Configurar o projeto Vue 3 com Vite, Tailwind e Pinia.
* **Estrutura da Tela:** Criar o layout macro consistindo em duas áreas principais:
    1.  Uma barra lateral estática (Sidebar) que abrigará o Chat da IA e a lista de módulos disponíveis.
    2.  A Área de Trabalho (Canvas) central ocupando o resto da tela (onde os widgets flutuarão).
* **Estado Mockado:** Criar uma store no Pinia `useDashboardStore` com um estado inicial contendo dados falsos de 2 widgets apenas para teste visual.

### Fase 2: O Motor de Física (Drag & Drop)
* **Implementação do Motion for Vue:** Criar o componente base `<DraggableWidget>`.
* **Comportamento:** O componente deve ser livremente arrastável dentro dos limites do Canvas (`dragConstraints`).
* **Sincronização de Estado:** Quando o usuário terminar de arrastar (evento `onDragEnd`), o componente deve despachar uma ação para o Pinia atualizar as novas coordenadas (X, Y) do widget, garantindo que ele não volte à posição original se a tela recarregar.

### Fase 3: Biblioteca de Componentes (Os Widgets)
* Criar o esqueleto visual padrão dos "Cartões Fortinet" (cabeçalho escuro, título, botão de fechar/excluir).
* Desenvolver 3 componentes de visualização genéricos (usando dados estáticos por enquanto):
    1.  `WidgetHealth` (Métricas de sistema: CPU, Memória).
    2.  `WidgetThreats` (Tabela de IPs bloqueados).
    3.  `WidgetNetwork` (Gráfico de rosca/donut para aplicações).

### Fase 4: Interface do "Natural Language to Dataview"
* **Chat UI:** Desenvolver a interface do chat na barra lateral.
* **Ação de Instanciamento:** Criar a função que simula a IA. Quando o usuário digitar um comando, o sistema deve adicionar um novo objeto ao array do Pinia, calculando uma posição vazia na tela, para que o `<DraggableWidget>` "nasça" no Canvas com uma animação suave.