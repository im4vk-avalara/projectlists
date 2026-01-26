"""
Tests for Access Manager

Paper Reference: Section 3.8
"""

import pytest
import asyncio

from aios.kernel.access_manager import (
    AccessManager,
    Permission,
    PrivilegeLevel,
    PrivilegeGroup,
)


class TestPrivilegeGroup:
    """Tests for PrivilegeGroup class."""
    
    def test_create_group(self):
        """Test creating a privilege group."""
        group = PrivilegeGroup(
            name="custom",
            level=PrivilegeLevel.USER,
            permissions={Permission.READ, Permission.WRITE},
        )
        
        assert group.name == "custom"
        assert group.has_permission(Permission.READ)
        assert group.has_permission(Permission.WRITE)
        assert not group.has_permission(Permission.DELETE)
    
    def test_admin_has_all_permissions(self):
        """Test admin level has all permissions."""
        group = PrivilegeGroup(
            name="admin",
            level=PrivilegeLevel.ADMIN,
            permissions=set(),  # Empty, but admin should have all
        )
        
        assert group.has_permission(Permission.READ)
        assert group.has_permission(Permission.DELETE)
        assert group.has_permission(Permission.ADMIN)
    
    def test_tool_access(self):
        """Test tool access control."""
        group = PrivilegeGroup(
            name="limited",
            level=PrivilegeLevel.USER,
            permissions={Permission.EXECUTE},
            allowed_tools={"tool1", "tool2"},
        )
        
        assert group.can_use_tool("tool1")
        assert group.can_use_tool("tool2")
        assert not group.can_use_tool("tool3")


class TestAccessManager:
    """Tests for AccessManager class."""
    
    @pytest.fixture
    def access_mgr(self) -> AccessManager:
        """Create access manager."""
        return AccessManager(default_group="user", auto_approve=True)
    
    @pytest.mark.asyncio
    async def test_register_agent(self, access_mgr: AccessManager):
        """Test registering an agent."""
        access = await access_mgr.register_agent("agent-1")
        
        assert access.agent_id == "agent-1"
        assert access.group.name == "user"
    
    @pytest.mark.asyncio
    async def test_check_permission(self, access_mgr: AccessManager):
        """Test permission checking."""
        await access_mgr.register_agent("agent-1", "user")
        
        # User has read/write/execute
        assert await access_mgr.check_permission("agent-1", Permission.READ)
        assert await access_mgr.check_permission("agent-1", Permission.WRITE)
        
        # User doesn't have admin
        assert not await access_mgr.check_permission("agent-1", Permission.ADMIN)
    
    @pytest.mark.asyncio
    async def test_guest_permissions(self, access_mgr: AccessManager):
        """Test guest privilege level."""
        await access_mgr.register_agent("guest-agent", "guest")
        
        # Guest only has read
        assert await access_mgr.check_permission("guest-agent", Permission.READ)
        assert not await access_mgr.check_permission("guest-agent", Permission.WRITE)
    
    @pytest.mark.asyncio
    async def test_grant_permission(self, access_mgr: AccessManager):
        """Test granting permissions."""
        await access_mgr.register_agent("agent-1", "guest")
        
        # Initially no write permission
        assert not await access_mgr.check_permission("agent-1", Permission.WRITE)
        
        # Grant write
        await access_mgr.grant_permission("agent-1", Permission.WRITE)
        
        # Now has write
        assert await access_mgr.check_permission("agent-1", Permission.WRITE)
    
    @pytest.mark.asyncio
    async def test_revoke_permission(self, access_mgr: AccessManager):
        """Test revoking permissions."""
        await access_mgr.register_agent("agent-1", "user")
        
        # Initially has write
        assert await access_mgr.check_permission("agent-1", Permission.WRITE)
        
        # Revoke write
        await access_mgr.revoke_permission("agent-1", Permission.WRITE)
        
        # No longer has write
        assert not await access_mgr.check_permission("agent-1", Permission.WRITE)
    
    @pytest.mark.asyncio
    async def test_resource_permission(self, access_mgr: AccessManager):
        """Test resource-level permissions."""
        await access_mgr.register_agent("agent-1", "guest")
        
        # Grant write on specific resource
        await access_mgr.grant_permission("agent-1", Permission.WRITE, "file.txt")
        
        # Has write on that resource
        assert await access_mgr.check_permission("agent-1", Permission.WRITE, "file.txt")
        
        # But not on other resources
        assert not await access_mgr.check_permission("agent-1", Permission.WRITE, "other.txt")
    
    @pytest.mark.asyncio
    async def test_cross_agent_access(self, access_mgr: AccessManager):
        """Test cross-agent access checks."""
        await access_mgr.register_agent("agent-1", "user")
        await access_mgr.register_agent("agent-2", "user")
        
        # By default, agents can interact
        assert await access_mgr.check_cross_agent_access(
            "agent-1", "agent-2", Permission.READ
        )
    
    @pytest.mark.asyncio
    async def test_tool_access(self, access_mgr: AccessManager):
        """Test tool access control."""
        await access_mgr.register_agent("agent-1", "user")
        
        # User can use all tools by default
        assert await access_mgr.check_tool_access("agent-1", "any_tool")
    
    @pytest.mark.asyncio
    async def test_confirmation_auto_approve(self, access_mgr: AccessManager):
        """Test auto-approval of confirmations."""
        await access_mgr.register_agent("agent-1")
        
        # With auto_approve=True, should return True immediately
        result = await access_mgr.request_confirmation(
            agent_id="agent-1",
            resource="important.txt",
            permission=Permission.DELETE,
            description="Delete important file",
        )
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_pending_requests(self, access_mgr: AccessManager):
        """Test getting pending requests."""
        # Create a manager without auto_approve
        mgr = AccessManager(auto_approve=False, confirmation_timeout=1)
        await mgr.register_agent("agent-1")
        
        # Start a confirmation request (don't await)
        task = asyncio.create_task(
            mgr.request_confirmation(
                "agent-1", "file.txt", Permission.DELETE, "Delete"
            )
        )
        
        await asyncio.sleep(0.1)
        
        # Should have pending request
        pending = mgr.get_pending_requests()
        assert len(pending) == 1
        
        # Approve it
        await mgr.approve_request(pending[0].request_id)
        
        result = await task
        assert result is True
    
    @pytest.mark.asyncio
    async def test_audit_log(self, access_mgr: AccessManager):
        """Test audit logging."""
        await access_mgr.register_agent("agent-1")
        await access_mgr.check_permission("agent-1", Permission.READ)
        await access_mgr.check_permission("agent-1", Permission.WRITE)
        
        log = access_mgr.get_audit_log(agent_id="agent-1")
        
        assert len(log) >= 2
        assert any(e["event_type"] == "permission_check" for e in log)
    
    @pytest.mark.asyncio
    async def test_create_custom_group(self, access_mgr: AccessManager):
        """Test creating custom privilege group."""
        access_mgr.create_group(
            name="readonly",
            level=PrivilegeLevel.GUEST,
            permissions={Permission.READ},
            memory_limit_mb=25,
        )
        
        await access_mgr.register_agent("agent-1", "readonly")
        
        assert await access_mgr.check_permission("agent-1", Permission.READ)
        assert not await access_mgr.check_permission("agent-1", Permission.WRITE)
    
    @pytest.mark.asyncio
    async def test_stats(self, access_mgr: AccessManager):
        """Test getting stats."""
        await access_mgr.register_agent("agent-1")
        await access_mgr.register_agent("agent-2")
        
        stats = access_mgr.get_stats()
        
        assert stats["registered_agents"] == 2
        assert "user" in stats["privilege_groups"]

