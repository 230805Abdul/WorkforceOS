resource "aws_secretsmanager_secret" "app_secret_key" {
  name = "${var.project_name}-${var.environment}-secret-key"
}

resource "random_password" "app_secret_key" {
  length  = 64
  special = false
}

resource "aws_secretsmanager_secret_version" "app_secret_key" {
  secret_id     = aws_secretsmanager_secret.app_secret_key.id
  secret_string = random_password.app_secret_key.result
}
