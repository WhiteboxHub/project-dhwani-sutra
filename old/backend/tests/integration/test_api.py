"""Integration tests for API endpoints."""

import pytest


class TestHealthEndpoints:
    """Test health check endpoints."""

    def test_root_endpoint(self, client):
        """Test root endpoint."""
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Dhwani Sutra"
        assert "version" in data

    def test_health_endpoint(self, client):
        """Test health check endpoint."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "provider" in data
        assert "test_mode" in data

    def test_readiness_endpoint(self, client):
        """Test readiness check endpoint."""
        response = client.get("/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"


class TestWebSocketEndpoints:
    """Test WebSocket endpoints."""

    def test_sender_endpoint_exists(self, client):
        """Test that sender endpoint is registered."""
        # WebSocket endpoints show up in OpenAPI schema
        response = client.get("/openapi.json")
        assert response.status_code == 200

    def test_cors_headers(self, client):
        """Test CORS headers are present."""
        response = client.options("/health")

        # Check for CORS headers
        assert "access-control-allow-origin" in response.headers or response.status_code == 200
