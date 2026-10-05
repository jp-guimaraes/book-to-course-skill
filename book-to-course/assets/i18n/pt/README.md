# Como rodar o curso

**Recomendado:** rode `start.bat` (Windows) ou `./start.sh` (macOS/Linux). É preciso ter Python 3 instalado.
O curso abre no seu navegador em http://127.0.0.1:8765. Isso dá acesso a:

- progresso salvo em `progress/progress.json` (você pode copiá-lo para outro computador),
- um botão **▶ Rodar testes** nos exercícios, que roda os testes automatizados com um clique.

**Sem Python:** dê duplo clique em `index.html`. Tudo funciona, mas o progresso fica só no navegador,
e os testes dos exercícios são rodados manualmente no terminal (o comando aparece em cada exercício).

> No Windows, se `python3` não funcionar, use `python` ou `py -3`.

## Exercícios de programação

Cada exercício tem uma pasta `exercises/<nome>/` com arquivos iniciais e testes. Edite os arquivos iniciais no seu
editor e rode os testes até todos passarem. Você pode ler os testes — eles descrevem o que o programa deve fazer.

## Atualizando o curso com novos capítulos

Descompacte o novo pacote por cima da pasta antiga (sobrescrevendo os arquivos). A pasta `progress/` não vem no
pacote, então seu progresso é mantido.
