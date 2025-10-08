"""
Authentication and Rate Limiting for EvidentFit API

Implements JWT-based authentication with tier-based rate limiting to control costs.
See docs/COST_MANAGEMENT.md for full strategy.
"""

import os
import json
from datetime import datetime, timedelta
from typing import Dict, Optional, Literal
from collections import defaultdict

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr

# JWT Configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-this-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30

# Security
security = HTTPBearer()

# User Tiers
UserTier = Literal["free", "email_gated", "premium"]

# Rate Limits (per 30 days)
RATE_LIMITS = {
    "free": {
        "queries_per_month": 10,
        "stacks_per_month": 3,
        "max_tokens_per_query": 5000
    },
    "email_gated": {
        "queries_per_month": 50,
        "stacks_per_month": 10,
        "max_tokens_per_query": 10000
    },
    "premium": {
        "queries_per_month": 1000,
        "stacks_per_month": 100,
        "max_tokens_per_query": 20000
    }
}

# In-memory storage (replace with Redis/database in production)
user_usage: Dict[str, Dict] = defaultdict(lambda: {
    "queries": 0,
    "stacks": 0,
    "reset_date": datetime.now()
})

# User whitelist (replace with database in production)
approved_users: Dict[str, Dict] = {}


class UserInfo(BaseModel):
    """User information from JWT token"""
    user_id: str
    email: str
    tier: UserTier


class TokenResponse(BaseModel):
    """JWT token response"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int = ACCESS_TOKEN_EXPIRE_DAYS * 24 * 60 * 60


class UsageStats(BaseModel):
    """User usage statistics"""
    tier: UserTier
    queries_used: int
    queries_limit: int
    stacks_used: int
    stacks_limit: int
    reset_date: str


def create_access_token(user_id: str, email: str, tier: UserTier) -> str:
    """
    Create JWT access token for authenticated user
    
    Args:
        user_id: Unique user identifier
        email: User email address
        tier: User tier (free, email_gated, premium)
        
    Returns:
        JWT token string
    """
    payload = {
        "user_id": user_id,
        "email": email,
        "tier": tier,
        "exp": datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS),
        "iat": datetime.utcnow()
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> UserInfo:
    """
    Verify JWT token and return user info
    
    Args:
        credentials: HTTP bearer token from request header
        
    Returns:
        UserInfo object with user_id, email, and tier
        
    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        return UserInfo(
            user_id=payload["user_id"],
            email=payload["email"],
            tier=payload["tier"]
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please log in again."
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token"
        )


def check_rate_limit(user: UserInfo, action: Literal["queries", "stacks"]) -> bool:
    """
    Check if user has exceeded their rate limit
    
    Args:
        user: UserInfo object from verify_token
        action: Action type ("queries" or "stacks")
        
    Returns:
        True if within limit, False if exceeded
    """
    usage = user_usage[user.user_id]
    
    # Reset monthly counters if period has elapsed
    if datetime.now() > usage["reset_date"] + timedelta(days=30):
        usage["queries"] = 0
        usage["stacks"] = 0
        usage["reset_date"] = datetime.now()
    
    # Get limit for user's tier
    limit = RATE_LIMITS[user.tier][f"{action}_per_month"]
    current = usage[action]
    
    # Check if limit exceeded
    if current >= limit:
        return False
    
    # Increment counter
    usage[action] += 1
    return True


def enforce_rate_limit(user: UserInfo, action: Literal["queries", "stacks"]) -> None:
    """
    Enforce rate limit and raise exception if exceeded
    
    Args:
        user: UserInfo object from verify_token
        action: Action type ("queries" or "stacks")
        
    Raises:
        HTTPException: If rate limit is exceeded
    """
    if not check_rate_limit(user, action):
        limit = RATE_LIMITS[user.tier][f"{action}_per_month"]
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Your {user.tier} tier allows {limit} {action} per month. "
                   f"Upgrade to premium for unlimited access."
        )


def get_usage_stats(user: UserInfo) -> UsageStats:
    """
    Get current usage statistics for a user
    
    Args:
        user: UserInfo object from verify_token
        
    Returns:
        UsageStats object with current usage and limits
    """
    usage = user_usage[user.user_id]
    limits = RATE_LIMITS[user.tier]
    
    # Reset if period elapsed
    if datetime.now() > usage["reset_date"] + timedelta(days=30):
        usage["queries"] = 0
        usage["stacks"] = 0
        usage["reset_date"] = datetime.now()
    
    return UsageStats(
        tier=user.tier,
        queries_used=usage["queries"],
        queries_limit=limits["queries_per_month"],
        stacks_used=usage["stacks"],
        stacks_limit=limits["stacks_per_month"],
        reset_date=usage["reset_date"].isoformat()
    )


def is_user_approved(email: str) -> bool:
    """
    Check if user email is in the approved whitelist
    
    Args:
        email: User email address
        
    Returns:
        True if approved, False otherwise
    """
    return email in approved_users


def add_approved_user(email: str, tier: UserTier = "email_gated") -> str:
    """
    Add a user to the approved whitelist
    
    Args:
        email: User email address
        tier: User tier (default: email_gated)
        
    Returns:
        user_id: Generated user ID
    """
    import uuid
    user_id = str(uuid.uuid4())
    approved_users[email] = {
        "user_id": user_id,
        "email": email,
        "tier": tier,
        "approved": True,
        "created_at": datetime.now().isoformat()
    }
    return user_id


def load_approved_users(filepath: str = "approved_users.json") -> None:
    """
    Load approved users from JSON file
    
    Args:
        filepath: Path to JSON file with approved users
    """
    global approved_users
    try:
        if os.path.exists(filepath):
            with open(filepath, "r") as f:
                approved_users = json.load(f)
    except Exception as e:
        print(f"Warning: Could not load approved users: {e}")


def save_approved_users(filepath: str = "approved_users.json") -> None:
    """
    Save approved users to JSON file
    
    Args:
        filepath: Path to JSON file
    """
    try:
        with open(filepath, "w") as f:
            json.dump(approved_users, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save approved users: {e}")


# Cost tracking
api_costs: Dict[str, float] = defaultdict(float)


def log_api_cost(user: UserInfo, endpoint: str, input_tokens: int, output_tokens: int) -> None:
    """
    Log API call for cost tracking
    
    Args:
        user: UserInfo object
        endpoint: API endpoint called
        input_tokens: Number of input tokens used
        output_tokens: Number of output tokens used
    """
    # Calculate cost (GPT-4o-mini pricing)
    input_cost = (input_tokens / 1_000_000) * 0.15
    output_cost = (output_tokens / 1_000_000) * 0.60
    total_cost = input_cost + output_cost
    
    # Track daily cost
    today = datetime.now().strftime("%Y-%m-%d")
    api_costs[today] += total_cost
    
    # Log entry
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "user_id": user.user_id,
        "email": user.email,
        "tier": user.tier,
        "endpoint": endpoint,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost": total_cost
    }
    
    # Append to log file
    try:
        with open("api_costs.jsonl", "a") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        print(f"Warning: Could not log API cost: {e}")


def get_daily_cost() -> float:
    """
    Get total API cost for today
    
    Returns:
        Total cost in dollars
    """
    today = datetime.now().strftime("%Y-%m-%d")
    return api_costs.get(today, 0.0)


def check_circuit_breaker(max_daily_cost: float = 10.0) -> None:
    """
    Check if daily cost exceeds threshold and raise exception
    
    Args:
        max_daily_cost: Maximum allowed daily cost in dollars
        
    Raises:
        HTTPException: If daily cost exceeds threshold
    """
    daily_cost = get_daily_cost()
    if daily_cost > max_daily_cost:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Service temporarily unavailable due to high demand. "
                   f"Daily cost limit reached: ${daily_cost:.2f}"
        )


# Load approved users on module import
load_approved_users()


