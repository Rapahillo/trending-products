import pytest
from httpx import AsyncClient


class TestRegister:
    async def test_register_success(self, client: AsyncClient):
        response = await client.post("/api/v1/auth/register", json={
            "email": "test@example.com",
            "password": "securepass123",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["data"]["email"] == "test@example.com"
        assert data["data"]["subscription_tier"] == "free"
        assert "password" not in data["data"]

    async def test_register_duplicate_email(self, client: AsyncClient):
        await client.post("/api/v1/auth/register", json={"email": "dupe@example.com", "password": "pass123"})
        response = await client.post("/api/v1/auth/register", json={"email": "dupe@example.com", "password": "pass456"})
        assert response.status_code == 409

    async def test_register_invalid_email(self, client: AsyncClient):
        response = await client.post("/api/v1/auth/register", json={"email": "not-an-email", "password": "pass123"})
        assert response.status_code == 422


class TestLogin:
    async def test_login_success(self, client: AsyncClient):
        await client.post("/api/v1/auth/register", json={"email": "login@example.com", "password": "mypassword"})
        response = await client.post("/api/v1/auth/login", json={"email": "login@example.com", "password": "mypassword"})
        assert response.status_code == 200
        assert "access_token" in response.json()["data"]

    async def test_login_wrong_password(self, client: AsyncClient):
        await client.post("/api/v1/auth/register", json={"email": "wrong@example.com", "password": "correct"})
        response = await client.post("/api/v1/auth/login", json={"email": "wrong@example.com", "password": "incorrect"})
        assert response.status_code == 401

    async def test_login_nonexistent_user(self, client: AsyncClient):
        response = await client.post("/api/v1/auth/login", json={"email": "noone@example.com", "password": "anything"})
        assert response.status_code == 401


class TestMe:
    async def test_get_me_authenticated(self, client: AsyncClient):
        await client.post("/api/v1/auth/register", json={"email": "me@example.com", "password": "mypass"})
        login = await client.post("/api/v1/auth/login", json={"email": "me@example.com", "password": "mypass"})
        token = login.json()["data"]["access_token"]
        response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json()["data"]["email"] == "me@example.com"

    async def test_get_me_unauthenticated(self, client: AsyncClient):
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 401
