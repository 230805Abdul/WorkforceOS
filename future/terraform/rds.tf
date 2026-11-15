resource "aws_db_subnet_group" "main" {
  name       = "${var.project_name}-db-subnets"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_db_instance" "postgres" {
  identifier     = "${var.project_name}-${var.environment}"
  engine         = "postgres"
  engine_version = "16"
  instance_class = var.db_instance_class

  allocated_storage     = 20
  max_allocated_storage = 100 # autoscaling ceiling - grows under load, doesn't surprise-bill unbounded
  storage_type           = "gp3"
  storage_encrypted      = true

  db_name  = "workforceos"
  username = var.db_username
  password = var.db_password

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false

  multi_az                = var.environment == "production"
  backup_retention_period = 7
  backup_window            = "03:00-04:00"
  maintenance_window        = "mon:04:30-mon:05:30"

  deletion_protection      = var.environment == "production"
  skip_final_snapshot      = var.environment != "production"
  final_snapshot_identifier = var.environment == "production" ? "${var.project_name}-final-snapshot" : null

  tags = { Name = "${var.project_name}-postgres" }
}

resource "aws_elasticache_subnet_group" "main" {
  name       = "${var.project_name}-redis-subnets"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id = "${var.project_name}-redis"
  description           = "Cache + Celery broker for ${var.project_name}"
  node_type              = "cache.t4g.micro"
  num_cache_clusters     = var.environment == "production" ? 2 : 1
  engine                 = "redis"
  engine_version         = "7.1"
  port                   = 6379

  subnet_group_name = aws_elasticache_subnet_group.main.name
  security_group_ids = [aws_security_group.redis.id]

  automatic_failover_enabled = var.environment == "production"
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true

  tags = { Name = "${var.project_name}-redis" }
}
