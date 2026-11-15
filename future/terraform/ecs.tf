resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-${var.environment}"
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${var.project_name}-api"
  retention_in_days = 30
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/ecs/${var.project_name}-worker"
  retention_in_days = 30
}

locals {
  db_url    = "postgresql+asyncpg://${var.db_username}:${var.db_password}@${aws_db_instance.postgres.endpoint}/workforceos"
  redis_url = "redis://${aws_elasticache_replication_group.redis.primary_endpoint_address}:6379/0"
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${var.project_name}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn             = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "api"
    image     = var.api_image
    essential = true
    portMappings = [{ containerPort = var.container_port, protocol = "tcp" }]
    environment = [
      { name = "APP_ENV", value = var.environment },
      { name = "DATABASE_URL", value = local.db_url },
      { name = "REDIS_URL", value = local.redis_url },
      { name = "CELERY_BROKER_URL", value = "${local.redis_url}1" },
    ]
    secrets = [
      { name = "SECRET_KEY", valueFrom = aws_secretsmanager_secret.app_secret_key.arn },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.api.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "api"
      }
    }
    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 10
    }
  }])
}

resource "aws_ecs_task_definition" "worker" {
  family                   = "${var.project_name}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn             = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "worker"
    image     = var.worker_image
    essential = true
    environment = [
      { name = "APP_ENV", value = var.environment },
      { name = "DATABASE_URL", value = local.db_url },
      { name = "REDIS_URL", value = local.redis_url },
      { name = "CELERY_BROKER_URL", value = "${local.redis_url}1" },
    ]
    secrets = [
      { name = "SECRET_KEY", valueFrom = aws_secretsmanager_secret.app_secret_key.arn },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.worker.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "worker"
      }
    }
  }])
}

resource "aws_lb" "main" {
  name               = "${var.project_name}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id
}

resource "aws_lb_target_group" "api" {
  name        = "${var.project_name}-api-tg"
  port        = var.container_port
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 30
    timeout             = 5
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.acm_certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

resource "aws_ecs_service" "api" {
  name            = "${var.project_name}-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.api_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = aws_subnet.private[*].id
    security_groups = [aws_security_group.ecs_tasks.id]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name    = "api"
    container_port    = var.container_port
  }

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent          = 200 # allows a full extra batch during rolling deploys - zero downtime

  depends_on = [aws_lb_listener.https]
}

resource "aws_ecs_service" "worker" {
  name            = "${var.project_name}-worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = 2
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = aws_subnet.private[*].id
    security_groups = [aws_security_group.ecs_tasks.id]
  }
}

# Auto-scale the API on CPU - demand-based, not a guess
resource "aws_appautoscaling_target" "api" {
  max_capacity       = 6
  min_capacity       = var.api_desired_count
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.api.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "api_cpu" {
  name               = "${var.project_name}-api-cpu-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.api.resource_id
  scalable_dimension = aws_appautoscaling_target.api.scalable_dimension
  service_namespace  = aws_appautoscaling_target.api.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value       = 65
    scale_in_cooldown  = 120
    scale_out_cooldown = 60
  }
}
