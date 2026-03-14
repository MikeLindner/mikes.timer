terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
  }
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

data "cloudflare_zone" "belairmoon" {
  name = "belairmoon.au"
}

resource "cloudflare_record" "duoclock" {
  zone_id = data.cloudflare_zone.belairmoon.id
  name    = "duoclock"
  content = var.device_ip
  type    = "A"
  ttl     = 300
  proxied = false
}

output "fqdn" {
  value = cloudflare_record.duoclock.hostname
}
