# AIOS Threat Model

This document describes the access control mechanisms, security boundaries, and user intervention surfaces in AIOS, based on Section 3.8 (Access Manager).

---

## Security Boundaries

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           TRUST BOUNDARY 1: User                             │
│                                                                              │
│   User provides input, approves irreversible operations, manages agents     │
│                                                                              │
├──────────────────────────────────────────┬──────────────────────────────────┤
│                                          │                                   │
│   TRUST BOUNDARY 2: Agent Applications   │   TRUST BOUNDARY 3: External     │
│   ┌────────────────────────────────────┐ │   ┌────────────────────────────┐ │
│   │  Agent A        Agent B            │ │   │   External APIs            │ │
│   │  (trusted)      (semi-trusted)     │ │   │   (untrusted)              │ │
│   │                                    │ │   │                            │ │
│   │  Can access:    Can access:        │ │   │  Weather API               │ │
│   │  - Own memory   - Own memory       │ │   │  Payment Gateway           │ │
│   │  - Own storage  - Own storage      │ │   │  Calendar API              │ │
│   │  - Shared files - Shared files     │ │   │                            │ │
│   │  - All tools    - Limited tools    │ │   └────────────────────────────┘ │
│   └────────────────────────────────────┘ │                                   │
│                                          │                                   │
├──────────────────────────────────────────┴──────────────────────────────────┤
│                                                                              │
│                           TRUST BOUNDARY 4: AIOS Kernel                      │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │                          Access Manager                               │  │
│   │   - Enforces all access control decisions                            │  │
│   │   - Mediates cross-agent resource access                             │  │
│   │   - Triggers user confirmation for irreversible ops                  │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Privilege Groups

### Group Hierarchy

```python
class PrivilegeLevel(Enum):
    """
    Privilege levels from least to most permissive.
    
    Paper Reference: Section 3.8 (privilege groups)
    """
    GUEST = 0       # Read-only access to public resources
    USER = 1        # Standard agent privileges
    ELEVATED = 2    # Access to sensitive operations
    ADMIN = 3       # Full system access

@dataclass
class PrivilegeGroup:
    """Define permissions for a privilege level."""
    level: PrivilegeLevel
    allowed_syscalls: Set[str]
    allowed_resources: Set[str]
    requires_confirmation: Set[str]  # Operations needing user approval
```

### Default Privilege Assignments

| Privilege Level | Allowed Operations | Resource Access | Confirmation Required |
|-----------------|-------------------|-----------------|----------------------|
| GUEST | `llm_chat`, `llm_generate` | Public shared files only | None |
| USER | All standard syscalls | Own memory, own storage, shared files | Payment, external API calls |
| ELEVATED | + Tool registration, sharing | + Other agents' shared resources | Deletion, irreversible external ops |
| ADMIN | All syscalls | All resources | None (full trust) |

---

## Access Control Model

### Permission Types

```python
class Permission(Enum):
    """
    Fine-grained permissions for resources.
    """
    READ = "read"           # View/retrieve resource
    WRITE = "write"         # Create/update resource
    DELETE = "delete"       # Remove resource
    EXECUTE = "execute"     # Run/invoke (tools, code)
    SHARE = "share"         # Grant access to others
    ADMIN = "admin"         # Manage permissions
```

### Resource Types

```python
class ResourceType(Enum):
    """
    Types of protected resources.
    """
    MEMORY = "memory"           # Short-term memory blocks
    STORAGE = "storage"         # Persistent files
    TOOL = "tool"               # Registered tools
    LLM = "llm"                 # LLM inference capacity
    CONTEXT = "context"         # LLM context snapshots
    EXTERNAL_API = "external"   # External service calls
```

### Access Control List (ACL) Structure

```python
@dataclass
class ACLEntry:
    """
    Single access control entry.
    """
    resource_id: str
    resource_type: ResourceType
    agent_id: str              # Agent this entry applies to ("*" for all)
    permissions: Set[Permission]
    granted_by: str            # Agent who granted this access
    granted_at: float
    expires_at: Optional[float] = None
    conditions: Dict[str, Any] = field(default_factory=dict)

class AccessControlList:
    """
    Complete ACL for the system.
    
    Paper Reference: Section 3.8
    """
    entries: List[ACLEntry]
    
    def check_access(
        self, 
        agent_id: str, 
        resource_id: str, 
        permission: Permission
    ) -> bool:
        """Check if agent has permission on resource."""
        matching_entries = [
            e for e in self.entries
            if (e.resource_id == resource_id and 
                (e.agent_id == agent_id or e.agent_id == "*") and
                permission in e.permissions and
                (e.expires_at is None or e.expires_at > time.time()))
        ]
        return len(matching_entries) > 0
```

---

## Cross-Agent Access Control

### Scenario: Agent A Wants to Access Agent B's Storage

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          CROSS-AGENT ACCESS FLOW                          │
└──────────────────────────────────────────────────────────────────────────┘

Agent A                    Access Manager                    Agent B's Storage
   │                            │                                  │
   │  1. storage_read(          │                                  │
   │     path="/agent_b/data")  │                                  │
   │ ─────────────────────────► │                                  │
   │                            │                                  │
   │                            │  2. Check ACL                    │
   │                            │     Is /agent_b/data shared      │
   │                            │     with Agent A?                │
   │                            │ ◄────────────────────────────────│
   │                            │                                  │
   │                            │  3a. If NOT shared:              │
   │  4a. PermissionDenied      │      return deny                 │
   │ ◄───────────────────────── │                                  │
   │                            │                                  │
   │                            │  3b. If shared with READ:        │
   │                            │      forward request             │
   │                            │ ─────────────────────────────────►
   │                            │                                  │
   │                            │                         5. Return data
   │                            │ ◄─────────────────────────────────
   │  6. StorageResponse(data)  │                                  │
   │ ◄───────────────────────── │                                  │
```

### Cross-Agent Access Rules

```python
class CrossAgentAccessPolicy:
    """
    Policies for cross-agent resource access.
    
    Paper Reference: Section 3.8 (cross-agent access checks)
    """
    
    # Default: agents can only access their own resources
    default_policy: str = "deny"
    
    # Sharing must be explicit
    sharing_requires_confirmation: bool = True
    
    # Maximum permission level that can be shared
    max_shareable_permission: Permission = Permission.READ
    
    # Resources that cannot be shared
    non_shareable_resources: Set[str] = {
        "context_snapshots",  # LLM state is private
        "api_keys",           # Credentials are private
        "user_data",          # PII is protected
    }
    
    def can_share(
        self,
        owner_agent: str,
        target_agent: str,
        resource: str,
        permission: Permission
    ) -> bool:
        """Check if sharing is allowed."""
        if resource in self.non_shareable_resources:
            return False
        if permission.value > self.max_shareable_permission.value:
            return False
        return True
```

---

## User Intervention Surfaces

### Irreversible Operations Requiring Confirmation

```python
IRREVERSIBLE_OPERATIONS = {
    # Storage operations
    "storage_delete": "Permanently delete file {path}",
    "storage_rollback": "Rollback {path} to version {version}, losing newer changes",
    
    # External operations
    "payment_process": "Process payment of ${amount} to {recipient}",
    "email_send": "Send email to {recipients}",
    "api_call_destructive": "Make destructive API call to {endpoint}",
    
    # System operations
    "agent_terminate": "Terminate agent {agent_id}",
    "memory_clear_all": "Clear all memory for agent {agent_id}",
    
    # Tool operations
    "tool_execute_code": "Execute code: {code_preview}",
    "tool_file_write_external": "Write to external file: {path}",
}
```

### User Confirmation Flow

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         USER CONFIRMATION FLOW                            │
└──────────────────────────────────────────────────────────────────────────┘

Agent                     Access Manager                         User
  │                            │                                   │
  │  1. payment_process(       │                                   │
  │     amount=500,            │                                   │
  │     recipient="Hotel X")   │                                   │
  │ ─────────────────────────► │                                   │
  │                            │                                   │
  │                            │  2. Operation is irreversible     │
  │                            │     Prepare confirmation request  │
  │                            │                                   │
  │                            │  3. Request confirmation          │
  │                            │     "Process payment of $500      │
  │                            │      to Hotel X?"                 │
  │                            │ ─────────────────────────────────►│
  │                            │                                   │
  │                            │                          4. User reviews
  │                            │                             and decides
  │                            │                                   │
  │                            │  5a. User approves               │
  │                            │ ◄─────────────────────────────────│
  │                            │                                   │
  │  6a. Continue execution    │                                   │
  │      → PaymentResponse     │                                   │
  │ ◄───────────────────────── │                                   │
  │                            │                                   │
  │                            │  5b. User denies                 │
  │                            │ ◄─────────────────────────────────│
  │                            │                                   │
  │  6b. OperationCancelled    │                                   │
  │ ◄───────────────────────── │                                   │
```

### Confirmation Request Implementation

```python
@dataclass
class ConfirmationRequest:
    """
    Request for user confirmation on irreversible operation.
    """
    request_id: str
    agent_id: str
    operation: str
    description: str
    risk_level: str  # "low", "medium", "high", "critical"
    details: Dict[str, Any]
    created_at: float
    expires_at: float
    status: str = "pending"  # "pending", "approved", "denied", "expired"

class UserConfirmationService:
    """
    Handles user confirmation requests.
    
    Paper Reference: Section 3.8 (user intervention)
    """
    
    async def request_confirmation(
        self,
        agent_id: str,
        operation: str,
        description: str,
        timeout: int = 60
    ) -> bool:
        """
        Request user confirmation for an operation.
        
        Returns True if approved, False if denied or timeout.
        """
        request = ConfirmationRequest(
            request_id=str(uuid.uuid4()),
            agent_id=agent_id,
            operation=operation,
            description=description,
            risk_level=self.assess_risk(operation),
            details=self.get_operation_details(operation),
            created_at=time.time(),
            expires_at=time.time() + timeout
        )
        
        # Notify user via configured channel (UI, email, etc.)
        await self.notify_user(request)
        
        # Wait for response with timeout
        try:
            response = await asyncio.wait_for(
                self.wait_for_response(request.request_id),
                timeout=timeout
            )
            return response.approved
        except asyncio.TimeoutError:
            request.status = "expired"
            return False
```

---

## Threat Scenarios and Mitigations

### Threat 1: Agent Privilege Escalation

**Scenario**: Malicious agent tries to access resources beyond its privilege level.

**Mitigations**:
- All syscalls pass through Access Manager before execution
- Privilege checks happen at kernel level, not agent level
- Agents cannot modify their own privilege level

```python
async def execute_syscall(syscall: Syscall):
    # ALWAYS check access first
    if not await access_manager.check_access(
        agent_id=syscall.agent_id,
        operation=syscall.operation,
        resource=syscall.resource
    ):
        raise PermissionDenied()
    
    # Only then execute
    return await do_execute(syscall)
```

### Threat 2: Cross-Agent Data Theft

**Scenario**: Agent A tries to read Agent B's private memory.

**Mitigations**:
- Memory is agent-indexed, access requires explicit share
- Storage paths are sandboxed per agent
- ACL checks on every cross-agent access attempt

```python
def memory_read(agent_id: str, key: str):
    # Memory keys are prefixed with agent_id
    full_key = f"{agent_id}:{key}"
    
    # Cannot access other agents' memory without share
    if not key.startswith(f"{calling_agent_id}:"):
        # Check if shared
        if not acl.check_access(calling_agent_id, full_key, Permission.READ):
            raise PermissionDenied()
```

### Threat 3: Unauthorized External Actions

**Scenario**: Agent tries to make payment without user consent.

**Mitigations**:
- Irreversible operations require user confirmation
- External API calls are logged and rate-limited
- High-risk tools require ELEVATED privilege

```python
async def tool_call(agent_id: str, tool_name: str, params: Dict):
    tool = tool_registry.get(tool_name)
    
    # Check privilege level
    if tool.requires_elevated and agent.privilege < PrivilegeLevel.ELEVATED:
        raise PermissionDenied("Elevated privileges required")
    
    # Check for irreversible operations
    if tool.is_irreversible:
        confirmed = await request_user_confirmation(
            agent_id=agent_id,
            operation=tool_name,
            description=tool.describe_action(params)
        )
        if not confirmed:
            raise OperationCancelled()
    
    return await tool.execute(params)
```

### Threat 4: Context Snapshot Leakage

**Scenario**: Agent tries to access another agent's LLM context/state.

**Mitigations**:
- Context snapshots are non-shareable resources
- Snapshots are encrypted at rest
- Only owning agent can restore its snapshots

```python
def context_restore(agent_id: str, snapshot_id: str):
    snapshot = context_store.get(snapshot_id)
    
    # Verify ownership
    if snapshot.agent_id != agent_id:
        raise PermissionDenied("Cannot restore another agent's context")
    
    return restore_snapshot(snapshot)
```

### Threat 5: Tool Injection/Hijacking

**Scenario**: Malicious tool registration to intercept calls.

**Mitigations**:
- Tool registration requires ELEVATED privilege
- Conflict resolution uses namespacing
- Tool integrity verified before execution

```python
def tool_register(agent_id: str, tool_schema: ToolSchema):
    # Require elevated privilege
    if agent.privilege < PrivilegeLevel.ELEVATED:
        raise PermissionDenied()
    
    # Namespace tool to prevent hijacking
    namespaced_name = f"{agent_id}/{tool_schema.name}"
    
    # Check for conflicts
    if namespaced_name in tool_registry:
        raise ToolConflict(f"Tool {namespaced_name} already exists")
    
    tool_registry.register(namespaced_name, tool_schema)
```

---

## Audit Logging

All access control decisions are logged for security auditing:

```python
@dataclass
class AuditLogEntry:
    """
    Audit log entry for access control events.
    """
    timestamp: float
    event_type: str  # "access_check", "permission_granted", "permission_denied", 
                     # "user_confirmation_requested", "user_confirmed", "user_denied"
    agent_id: str
    operation: str
    resource: str
    result: str
    details: Dict[str, Any]

class AuditLogger:
    """
    Security audit logging.
    """
    
    def log_access_check(
        self,
        agent_id: str,
        operation: str,
        resource: str,
        result: bool,
        reason: str = None
    ):
        entry = AuditLogEntry(
            timestamp=time.time(),
            event_type="access_check",
            agent_id=agent_id,
            operation=operation,
            resource=resource,
            result="allowed" if result else "denied",
            details={"reason": reason}
        )
        self.store(entry)
```

---

## References

- Paper Section 3.8: Access Manager
- Figure 1: Shows operations requiring OS vs LLM management (implicit trust levels)
- Figure 2: Shows Access Manager as kernel module

