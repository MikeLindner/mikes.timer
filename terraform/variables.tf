variable "cloudflare_api_token" {
  description = "Cloudflare API token with DNS edit permissions for belairmoon.au"
  type        = string
  sensitive   = true
}

variable "device_ip" {
  description = "Static IP address assigned to the ESP32 on the local network"
  type        = string
  default     = "192.168.1.200"
}
