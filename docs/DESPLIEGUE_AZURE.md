# Despliegue en Azure (VM Standard_B2ms)

Todo el sistema (PostgreSQL, backend, worker, frontend y Caddy con HTTPS) corre con
`docker compose` en una sola VM Ubuntu 24.04 de 2 vCPU y 8 GB de RAM.
Costo aproximado: **US$66/mes** (VM ~60, disco 30 GB ~2.5, IP pública ~3.5).

| Archivo | Qué hace | Dónde se ejecuta |
|---|---|---|
| `infra/deploy/crear-vm.sh` | Crea grupo de recursos, VM, IP con DNS y abre 80/443 | Azure Cloud Shell |
| `infra/deploy/empaquetar.sh` | Genera `despliegue/` con código, `bd.dump` y `ml_artifacts.tgz` | PC local (Git Bash) |
| `infra/deploy/instalar.sh` | Instala Docker, crea `.env.prod`, restaura datos y levanta todo | VM |
| `infra/deploy/respaldar.sh` | Respalda BD y modelos antes de borrar la VM | VM |
| `infra/docker-compose.prod.yml` | Compose de producción (sin puertos internos expuestos ni `--reload`) | VM |

## 1. Llave SSH (PC local, una sola vez)

```powershell
ssh-keygen -t ed25519
Get-Content $HOME\.ssh\id_ed25519.pub
```

Copie la línea que imprime (empieza con `ssh-ed25519`).

## 2. Crear la VM (Azure Cloud Shell)

En https://portal.azure.com abra **Cloud Shell** (icono `>_`, modo Bash), suba
`infra/deploy/crear-vm.sh` con el botón **Cargar archivos** y ejecute:

```bash
SSH_PUB="ssh-ed25519 AAAA...pegue-aquí" DNS_LABEL=ds-predictive-wehl bash crear-vm.sh
```

Al terminar muestra el dominio, por ejemplo `ds-predictive-wehl.eastus2.cloudapp.azure.com`.
Si Azure for Students rechaza la región o el tamaño, repita con otra región:
`UBICACION=centralus` (o `westus2`, `southcentralus`).

## 3. Empaquetar y subir (PC local, Git Bash, con Docker local levantado)

```bash
bash infra/deploy/empaquetar.sh
scp despliegue/* azureuser@<dominio>:~
```

## 4. Instalar en la VM

```bash
ssh azureuser@<dominio>
mkdir -p ds-predictive && tar xzf ~/codigo.tgz -C ds-predictive
cd ds-predictive
bash infra/deploy/instalar.sh <dominio>
```

La primera vez tarda ~5–10 min (instala Docker y compila las imágenes). Luego abra
`https://<dominio>`. Caddy obtiene el certificado HTTPS solo; si al inicio muestra error de
certificado, espere un minuto y recargue (`docker logs ds-caddy` muestra el avance).

**Importante:** cambie de inmediato las claves de `admin@ds.gt` y `liquidador@ds.gt`, porque
las iniciales están escritas en `COMANDOS_LEVANTAR.txt`.

## Actualizar el código después

```bash
# PC local
bash infra/deploy/empaquetar.sh
scp despliegue/codigo.tgz azureuser@<dominio>:~
# VM
cd ~/ds-predictive && tar xzf ~/codigo.tgz && bash infra/deploy/instalar.sh <dominio>
```

`instalar.sh` no vuelve a restaurar la BD ni los modelos si ya tienen datos, y conserva
`.env.prod`.

## Operación

```bash
cd ~/ds-predictive
docker compose -f infra/docker-compose.prod.yml --env-file .env.prod ps
docker compose -f infra/docker-compose.prod.yml --env-file .env.prod logs -f backend
```

## Dar de baja (al terminar el mes)

```bash
# VM
cd ~/ds-predictive && bash infra/deploy/respaldar.sh
# PC local
scp -r azureuser@<dominio>:~/respaldo-* backups/
# Cloud Shell: borra VM, disco, IP y red de una vez
az group delete --name rg-ds-predictive --yes
```

Detener la VM desde el portal (**Detener**, que la desasigna) deja de cobrar la VM pero sigue
cobrando disco e IP (~US$6/mes).
