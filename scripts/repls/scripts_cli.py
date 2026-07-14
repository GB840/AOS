#!/usr/bin/env python3
"""
Script Runner REPL - Execute scripts as AOS capabilities.

This is the P0B front-end: user selects from available scripts and executes them
without needing to know about capabilities or routing.
"""

import sys
import os
import time

# Add src to path for fabric imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

from kernel.plugins.fabric_hub import FabricHub


def list_available_scripts(hub):
    """List all available script capabilities."""
    scripts_engine = hub.resolve_engine("scripts")
    if not scripts_engine:
        return []
    
    adapter = hub._registry._adapters[scripts_engine]
    caps = adapter.advertise_capabilities()
    
    # Filter script capabilities
    scripts = []
    for cap in caps:
        if isinstance(cap, str) and cap.startswith("script."):
            script_name = cap.replace("script.", "")
            scripts.append(script_name)
    
    return scripts


def main():
    print("🎯 AOS Scripts Runner")
    print("   Run Python scripts as AOS capabilities")
    print("   Scripts auto-discovered from scripts/repls/ directory")
    print("   " + "="*60)
    
    try:
        hub = FabricHub()
        print(f"✅ FabricHub loaded")
        
    except Exception as e:
        print(f"❌ Failed to load FabricHub: {e}")
        return 1
    
    running = True
    refresh_counter = 0
    
    while running:
        scripts = list_available_scripts(hub)
        refresh_counter += 1
        
        # Every 20 cycles, show a refresh indicator
        if refresh_counter % 20 == 0:
            print("🔄 Refreshing script list...")
        
        print(f"\n📜 Available scripts ({len(scripts)}):" if scripts else "\n📜 No scripts found")
        
        for i, script in enumerate(scripts, 1):
            print(f"  {i}. {script}")
        
        print("\nCommands:")
        print("  1-N  : Run script by number")
        print("  l    : List scripts")
        print("  r    : Refresh (check for new scripts)")
        print("  q    : Quit")
        
        try:
            choice = input(f"\n>> ").strip()
            
            if not choice:
                continue
            
            if choice.lower() == 'q':
                print("Goodbye!")
                running = False
            elif choice.lower() == 'l' or choice.lower() == 'r':
                print("🔄 Reloading script list...")
                # Force reload by invoking any capability on scripts engine
                if scripts:
                    hub.route(f"script.{scripts[0]}", {"name": "refresh"})
                    time.sleep(0.5)  # Give it time to reload
            elif choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(scripts):
                    script_name = scripts[idx]
                    print(f"\n⚡ Running '{script_name}'...")
                    
                    try:
                        start_time = time.perf_counter()
                        result = hub.route(f"script.{script_name}", payload={
                            "interactive": True,
                            "name": "User"
                        })
                        duration = time.perf_counter() - start_time
                        
                        if result.ok:
                            print(f"✅ Success ({duration:.2f}s)")
                            if result.data:
                                print(f"   Result: {result.data}")
                        else:
                            print(f"❌ Failed: {result.error}")
                    
                    except Exception as e:
                        print(f"❌ Error running script: {e}")
                else:
                    print(f"❌ Invalid script number: {choice}")
            else:
                print(f"❌ Unknown command: {choice}")
        
        except EOFError:
            print("\nGoodbye!")
            break
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())