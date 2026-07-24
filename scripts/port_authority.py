#!/usr/bin/env python
"""
PORT AUTHORITY - Zero-Conflict Port Management System

Abstract port allocation with friendly DNS names for local development.
Inspired by the Curtis AI OS PORT AUTHORITY system.

Features:
- Automatic port discovery (finds available ports)
- Friendly DNS names (*.pa.local)
- Port state persistence
- Conflict resolution
- Cross-project compatibility
"""

import socket
import json
import os
from pathlib import Path
from typing import Optional, Dict
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class PortAllocation:
    """A port allocation record."""
    service: str
    port: int
    dns_name: str
    allocated_at: str
    last_checked: str


class PortAuthority:
    """
    Port Authority - Zero-conflict port management system.

    Allocates available ports and creates friendly DNS names for services.
    """

    PORT_RANGE = (8000, 9999)  # Range for dynamic allocation
    STATE_FILE = Path.home() / ".port-authority" / "state.json"

    def __init__(self, project_name: str):
        self.project_name = project_name.lower().replace(" ", "-")
        self._state: Dict[str, PortAllocation] = {}
        self._load_state()

    def _load_state(self) -> None:
        """Load port state from disk."""
        if self.STATE_FILE.exists():
            try:
                data = json.loads(self.STATE_FILE.read_text())
                for name, alloc in data.items():
                    self._state[name] = PortAllocation(**alloc)
            except Exception:
                self._state = {}

    def _save_state(self) -> None:
        """Save port state to disk."""
        self.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {k: asdict(v) for k, v in self._state.items()}
        self.STATE_FILE.write_text(json.dumps(data, indent=2))

    def _is_port_available(self, port: int) -> bool:
        """Check if a port is available."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return True
        except OSError:
            return False

    def _find_available_port(self, preferred: Optional[int] = None) -> int:
        """Find an available port in the range."""
        if preferred and self._is_port_available(preferred):
            return preferred

        for port in range(self.PORT_RANGE[0], self.PORT_RANGE[1]):
            if self._is_port_available(port):
                return port

        raise RuntimeError(f"No available ports in range {self.PORT_RANGE}")

    def _verify_allocation(self, allocation: PortAllocation) -> bool:
        """Verify that a previously allocated port is still available."""
        return self._is_port_available(allocation.port)

    def allocate_port(
        self,
        service: str,
        preferred_port: Optional[int] = None,
        dns_suffix: str = "pa.local"
    ) -> PortAllocation:
        """
        Allocate a port for a service.

        Args:
            service: Service name (e.g., "api", "dashboard", "postgres")
            preferred_port: Preferred port number (will be used if available)
            dns_suffix: DNS suffix for friendly names (default: pa.local)

        Returns:
            PortAllocation with allocated port and DNS name
        """
        cache_key = f"{self.project_name}-{service}"

        # Check if we already have an allocation
        if cache_key in self._state:
            allocation = self._state[cache_key]
            if self._verify_allocation(allocation):
                # Update last checked time
                allocation.last_checked = datetime.utcnow().isoformat()
                self._save_state()
                return allocation
            else:
                # Port is taken, remove old allocation
                del self._state[cache_key]

        # Find available port
        port = self._find_available_port(preferred_port)

        # Create DNS name
        dns_name = f"{self.project_name}-{service}.{dns_suffix}"

        # Create allocation
        allocation = PortAllocation(
            service=service,
            port=port,
            dns_name=dns_name,
            allocated_at=datetime.utcnow().isoformat(),
            last_checked=datetime.utcnow().isoformat(),
        )

        self._state[cache_key] = allocation
        self._save_state()

        return allocation

    def get_allocation(self, service: str) -> Optional[PortAllocation]:
        """Get existing allocation for a service."""
        cache_key = f"{self.project_name}-{service}"
        return self._state.get(cache_key)

    def release_port(self, service: str) -> None:
        """Release a port allocation."""
        cache_key = f"{self.project_name}-{service}"
        if cache_key in self._state:
            del self._state[cache_key]
            self._save_state()

    def get_host_file_path(self) -> Path:
        """Get the path to the hosts file for DNS configuration."""
        if os.name == "nt":
            return Path("C:/Windows/System32/drivers/etc/hosts")
        return Path("/etc/hosts")

    def update_hosts_file(self, allocations: list[PortAllocation]) -> bool:
        """
        Update the system hosts file with DNS entries.

        Note: This requires administrator privileges.
        On Windows, run as Administrator.
        On Linux/Mac, run with sudo.
        """
        hosts_file = self.get_host_file_path()

        try:
            content = hosts_file.read_text()
            lines = content.splitlines()

            # Remove old entries for this project
            marker_start = f"# PORT AUTHORITY: {self.project_name}"
            marker_end = f"# END PORT AUTHORITY: {self.project_name}"
            new_lines = []
            skipping = False

            for line in lines:
                if marker_start in line:
                    skipping = True
                    continue
                if marker_end in line:
                    skipping = False
                    continue
                if not skipping:
                    new_lines.append(line)

            # Add new entries
            new_lines.append("")
            new_lines.append(marker_start)
            for alloc in allocations:
                new_lines.append(f"127.0.0.1       {alloc.dns_name} # {alloc.service}")
            new_lines.append(marker_end)
            new_lines.append("")

            hosts_file.write_text("\n".join(new_lines))
            return True
        except PermissionError:
            return False

    def print_status(self) -> None:
        """Print current port allocations."""
        print(f"\n{'='*60}")
        print(f"PORT AUTHORITY - {self.project_name.upper()}")
        print(f"{'='*60}")

        if not self._state:
            print("No ports allocated yet.")
            return

        for cache_key, alloc in self._state.items():
            status = "[OK]" if self._verify_allocation(alloc) else "[TAKEN]"
            print(f"  {alloc.service:15} -> {alloc.port:5}  {alloc.dns_name:40} {status}")

        print(f"{'='*60}\n")


def main():
    """CLI interface for Port Authority."""
    import argparse

    parser = argparse.ArgumentParser(description="PORT AUTHORITY - Port Management")
    parser.add_argument("project", help="Project name")
    parser.add_argument("service", help="Service name (e.g., api, dashboard)")
    parser.add_argument("--port", type=int, help="Preferred port (optional)")
    parser.add_argument("--list", action="store_true", help="List all allocations")
    parser.add_argument("--hosts", action="store_true", help="Update hosts file (requires admin)")

    args = parser.parse_args()

    pa = PortAuthority(args.project)

    if args.list:
        pa.print_status()
    elif args.hosts:
        allocations = list(pa._state.values())
        if pa.update_hosts_file(allocations):
            print("✓ Hosts file updated successfully!")
            print("  Note: Flush DNS cache if needed:")
            print("  - Windows: ipconfig /flushdns")
            print("  - Linux: sudo systemd-resolve --flush-caches")
        else:
            print("✗ Failed to update hosts file (run as Administrator/sudo)")
    else:
        alloc = pa.allocate_port(args.service, args.port)
        print(f"Allocated port {alloc.port} for {args.service}")
        print(f"DNS: {alloc.dns_name}")
        print(f"URL: http://{alloc.dns_name}")


if __name__ == "__main__":
    main()
