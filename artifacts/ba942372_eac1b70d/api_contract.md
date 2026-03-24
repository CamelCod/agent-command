### API Gateway
- **Chosen**: NGINX Ingress Controller (Kubernetes)
  - Version: 1.25+
  - Justification: Native TLS 1.3 support, efficient reverse proxying, widespread operational knowledge
  - Rejected: Kong (unnecessary complexity for simple routing), AWS API Gateway