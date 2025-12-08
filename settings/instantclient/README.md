# Instant Client layout

Coloque aqui os pacotes do Oracle Instant Client para cada plataforma:

- `windows/`: descompacte o Instant Client utilizado no Windows (ex.: `instantclient_23_0`).
- `linux/`: armazene os arquivos `.zip` para a build Docker (ex.: `instantclient-basiclite-linux.x64-23.5.0.24.07.zip`).

O `Dockerfile` procura zips diretamente em `settings/instantclient/linux/*.zip` e os instala em `/opt/oracle/instantclient`.
No Windows local, o CLI procura automaticamente o diretório `settings/instantclient/windows/instantclient_23_0` se `ORACLE_INSTANT_CLIENT` não estiver definido.
