"""
Tractum adapters — drop consensus into other frameworks.

Each module is an optional bridge: lazy-import the framework so the core
`tractum` package stays 4-dep lean. Install the framework yourself, then
import the adapter.
"""
