#!/usr/bin/env bash
# Crea la VM de producción en Azure. Se ejecuta en Azure Cloud Shell (Bash), que ya trae `az`.
#   SSH_PUB="ssh-ed25519 AAAA... usuario@pc" bash crear-vm.sh
# Variables opcionales: RG, UBICACION, VM, DNS_LABEL.
set -euo pipefail

RG="${RG:-rg-ds-predictive}"
UBICACION="${UBICACION:-eastus2}"
VM="${VM:-vm-ds-predictive}"
DNS_LABEL="${DNS_LABEL:-ds-predictive-$RANDOM}"
: "${SSH_PUB:?Defina SSH_PUB con el contenido de su llave pública (~/.ssh/id_ed25519.pub)}"

az group create --name "$RG" --location "$UBICACION" --output none

az vm create \
  --resource-group "$RG" \
  --name "$VM" \
  --image Ubuntu2404 \
  --size Standard_B2ms \
  --admin-username azureuser \
  --ssh-key-values "$SSH_PUB" \
  --os-disk-size-gb 30 \
  --storage-sku StandardSSD_LRS \
  --public-ip-sku Standard \
  --public-ip-address-dns-name "$DNS_LABEL" \
  --output none

# 22 queda abierto por defecto; se abren 80 (reto de Let's Encrypt) y 443.
az vm open-port --resource-group "$RG" --name "$VM" --port 80,443 --priority 1010 --output none

FQDN="$(az network public-ip list --resource-group "$RG" --query "[0].dnsSettings.fqdn" -o tsv)"
echo
echo "VM lista."
echo "  Dominio : $FQDN"
echo "  SSH     : ssh azureuser@$FQDN"
