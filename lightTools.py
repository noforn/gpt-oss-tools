import os
from kasa import Discover, KasaException, Module
import asyncio
from dotenv import load_dotenv
import traceback
from agents import function_tool
from statusTools import mark_adjusting_lights, clear_tool_status, mark_checking_status


FIRST_IP_ADDRESS = "192.168.1.165"
SECOND_IP_ADDRESS = "192.168.1.37"

@function_tool
async def turn_on_light() -> list[dict]:
    """Turns the lights on."""
    mark_adjusting_lights()
    try:
        ip_addresses_to_run_on = [FIRST_IP_ADDRESS, SECOND_IP_ADDRESS]

        async def _execute_turn_on_for_ip(target_ip: str):
            try:
                print(f"\n[turn_on_light_op_for_{target_ip}] Attempting to turn ON device...")
                dev = await Discover.discover_single(target_ip, timeout=5)
                await dev.turn_on()
                await dev.update()
                is_on_state = dev.is_on
                print(f"[turn_on_light_op_for_{target_ip}] Device is now {'ON' if is_on_state else 'OFF'}.")
                return {
                    "ip_address": target_ip,
                    "status": "success",
                    "message": f"Successfully turned on the light at {target_ip}. Current state: {'on' if is_on_state else 'off'}"
                }
            except KasaException as e:
                print(f"[turn_on_light_op_for_{target_ip}] Kasa Error: {e}")
                return {
                    "ip_address": target_ip,
                    "status": "error",
                    "message": f"Kasa Error for {target_ip} (turn_on): {str(e)}"
                }
            except asyncio.TimeoutError:
                print(f"[turn_on_light_op_for_{target_ip}] Timeout discovering device.")
                return {
                    "ip_address": target_ip,
                    "status": "error",
                    "message": f"Timeout discovering {target_ip} (turn_on)."}
            except Exception as e:
                print(f"[turn_on_light_op_for_{target_ip}] Unexpected error: {e}")
                return {
                    "ip_address": target_ip,
                    "status": "error",
                    "message": f"Unexpected error ({type(e).__name__}) for {target_ip} (turn_on): {str(e)}"
                }
        
        print(f"\n[turn_on_light] Initiating turn ON for: {', '.join(ip_addresses_to_run_on)}")
        
        tasks_to_run = [_execute_turn_on_for_ip(ip) for ip in ip_addresses_to_run_on]
        results = await asyncio.gather(*tasks_to_run)
        
        print(f"[turn_on_light] Completed turn ON operations.")
        return results
    finally:
        clear_tool_status()

@function_tool
async def turn_off_light() -> list[dict]:
    """Turns the lights off."""
    mark_adjusting_lights()
    try:
        ip_addresses_to_run_on = [FIRST_IP_ADDRESS, SECOND_IP_ADDRESS]

        async def _execute_turn_off_for_ip(target_ip: str):
            try:
                print(f"\n[turn_off_light_op_for_{target_ip}] Attempting to turn OFF device...")
                dev = await Discover.discover_single(target_ip, timeout=5)
                await dev.turn_off()
                await dev.update()
                is_on_state = dev.is_on
                print(f"[turn_off_light_op_for_{target_ip}] Device is now {'ON' if is_on_state else 'OFF'}.")
                return {
                    "ip_address": target_ip,
                    "status": "success",
                    "message": f"Successfully turned off the light at {target_ip}. Current state: {'on' if is_on_state else 'off'}"
                }
            except KasaException as e:
                print(f"[turn_off_light_op_for_{target_ip}] Kasa Error: {e}")
                return {
                    "ip_address": target_ip,
                    "status": "error",
                    "message": f"Kasa Error for {target_ip} (turn_off): {str(e)}"
                }
            except asyncio.TimeoutError:
                print(f"[turn_off_light_op_for_{target_ip}] Timeout discovering device.")
                return {
                    "ip_address": target_ip,
                    "status": "error",
                    "message": f"Timeout discovering {target_ip} (turn_off)."}
            except Exception as e:
                print(f"[turn_off_light_op_for_{target_ip}] Unexpected error: {e}")
                return {
                    "ip_address": target_ip,
                    "status": "error",
                    "message": f"Unexpected error ({type(e).__name__}) for {target_ip} (turn_off): {str(e)}"
                }
        
        print(f"\n[turn_off_light] Initiating turn OFF for: {', '.join(ip_addresses_to_run_on)}")
        
        tasks_to_run = [_execute_turn_off_for_ip(ip) for ip in ip_addresses_to_run_on]
        results = await asyncio.gather(*tasks_to_run)
        
        print(f"[turn_off_light] Completed turn OFF operations.")
        return results
    finally:
        clear_tool_status()


@function_tool
async def set_light_brightness(brightness: int) -> list[dict]:
    """
    Sets the brightness of the predefined Kasa smart lights.
    Args:
        brightness (int): The desired brightness level (0-100).
                          0 effectively turns the light off, 100 is full brightness.
    """
    mark_adjusting_lights()
    try:
        ip_addresses_to_run_on = [FIRST_IP_ADDRESS, SECOND_IP_ADDRESS]

        async def _execute_set_brightness_for_ip(target_ip: str, brightness_value: int):
            operation_name = f"set_brightness_to_{brightness_value}%"
            try:
                print(f"\n[{operation_name}_op_for_{target_ip}] Attempting operation...")

                if not (0 <= brightness_value <= 100):
                    message = f"Invalid brightness value: {brightness_value}. Must be between 0 and 100."
                    print(f"[{operation_name}_op_for_{target_ip}] {message}")
                    return {"ip_address": target_ip, "status": "error", "message": message}

                dev = await Discover.discover_single(target_ip, timeout=7)

                if dev is None:
                    message = f"Device not found at {target_ip}."
                    print(f"[{operation_name}_op_for_{target_ip}] {message}")
                    return {"ip_address": target_ip, "status": "error", "message": message}

                await dev.update()

                if not dev.is_dimmable:
                    message = f"Device {target_ip} is not dimmable."
                    print(f"[{operation_name}_op_for_{target_ip}] {message}")
                    return {"ip_address": target_ip, "status": "error", "message": message}

                if not hasattr(dev, 'modules') or dev.modules is None:
                    message = f"Device {target_ip} 'modules' attribute missing or None after update."
                    print(f"[{operation_name}_op_for_{target_ip}] {message}")
                    return {"ip_address": target_ip, "status": "error", "message": message}

                light_module = dev.modules.get(Module.Light)
                if light_module is None:
                    available_modules = list(dev.modules.keys()) if dev.modules else "None"
                    message = f"Light module not found for {target_ip}. Available modules: {available_modules}"
                    print(f"[{operation_name}_op_for_{target_ip}] {message}")
                    return {"ip_address": target_ip, "status": "error", "message": message}

                await light_module.set_brightness(brightness_value)
                await dev.update()
                current_brightness = light_module.brightness

                message = f"Successfully set brightness for {target_ip}. Current brightness: {current_brightness}%"
                print(f"[{operation_name}_op_for_{target_ip}] {message}")
                return {
                    "ip_address": target_ip,
                    "status": "success",
                    "brightness": current_brightness,
                    "message": message
                }
            except KasaException as e:
                message = f"Kasa Error for {target_ip} ({operation_name}): {str(e)}"
                print(f"[{operation_name}_op_for_{target_ip}] {message}")
                return {"ip_address": target_ip, "status": "error", "message": message}
            except asyncio.TimeoutError:
                message = f"Timeout during operation for {target_ip} ({operation_name})."
                print(f"[{operation_name}_op_for_{target_ip}] {message}")
                return {"ip_address": target_ip, "status": "error", "message": message}
            except Exception as e:
                message = f"Unexpected error for {target_ip} ({operation_name}): {type(e).__name__} - {str(e)}"
                print(f"[{operation_name}_op_for_{target_ip}] {message}")
                traceback.print_exc()
                return {"ip_address": target_ip, "status": "error", "message": message}

        print(f"\n[set_light_brightness] Initiating set brightness to {brightness}% for: {', '.join(ip_addresses_to_run_on)}")

        tasks_to_run = [_execute_set_brightness_for_ip(ip, brightness) for ip in ip_addresses_to_run_on]
        results = await asyncio.gather(*tasks_to_run)

        print(f"[set_light_brightness] Completed set brightness operations.")
        return results
    finally:
        clear_tool_status()

@function_tool
async def set_light_hsv(hue: int, saturation: int, value: int) -> list[dict]:
    """
    Sets the HSV (Hue, Saturation, Value) color of the predefined Kasa smart lights.
    Args:
        hue (int): The desired hue (0-360 degrees).
        saturation (int): The desired saturation (0-100 percent).
        value (int): The desired value/brightness (0-100 percent).
    """
    mark_adjusting_lights()
    try:
        ip_addresses_to_run_on = [FIRST_IP_ADDRESS, SECOND_IP_ADDRESS]

        async def _execute_set_hsv_for_ip(target_ip: str, hue_val: int, sat_val: int, val_val: int):
            operation_name = f"set_hsv_to_({hue_val},{sat_val},{val_val})"
            try:
                print(f"\n[{operation_name}_op_for_{target_ip}] Attempting operation...")

                if not (0 <= hue_val <= 360):
                    message = f"Invalid hue value: {hue_val}. Must be between 0 and 360."
                    print(f"[{operation_name}_op_for_{target_ip}] {message}")
                    return {"ip_address": target_ip, "status": "error", "message": message}
                if not (0 <= sat_val <= 100):
                    message = f"Invalid saturation value: {sat_val}. Must be between 0 and 100."
                    print(f"[{operation_name}_op_for_{target_ip}] {message}")
                    return {"ip_address": target_ip, "status": "error", "message": message}
                if not (0 <= val_val <= 100):
                    message = f"Invalid value/brightness: {val_val}. Must be between 0 and 100."
                    print(f"[{operation_name}_op_for_{target_ip}] {message}")
                    return {"ip_address": target_ip, "status": "error", "message": message}

                dev = await Discover.discover_single(target_ip, timeout=7)

                if dev is None:
                    message = f"Device not found at {target_ip}."
                    print(f"[{operation_name}_op_for_{target_ip}] {message}")
                    return {"ip_address": target_ip, "status": "error", "message": message}

                await dev.update()

                if not dev.is_color:
                    message = f"Device {target_ip} does not support color (HSV) changes."
                    print(f"[{operation_name}_op_for_{target_ip}] {message}")
                    return {"ip_address": target_ip, "status": "error", "message": message}

                if not hasattr(dev, 'modules') or dev.modules is None:
                    message = f"Device {target_ip} 'modules' attribute missing or None after update."
                    print(f"[{operation_name}_op_for_{target_ip}] {message}")
                    return {"ip_address": target_ip, "status": "error", "message": message}

                light_module = dev.modules.get(Module.Light)
                if light_module is None:
                    available_modules = list(dev.modules.keys()) if dev.modules else "None"
                    message = f"Light module not found for {target_ip}. Available modules: {available_modules}"
                    print(f"[{operation_name}_op_for_{target_ip}] {message}")
                    return {"ip_address": target_ip, "status": "error", "message": message}

                await light_module.set_hsv(hue_val, sat_val, val_val)
                await dev.update()
                current_hsv = light_module.hsv

                message = f"Successfully set HSV for {target_ip}. Current HSV: {current_hsv}"
                print(f"[{operation_name}_op_for_{target_ip}] {message}")
                return {
                    "ip_address": target_ip,
                    "status": "success",
                    "hsv": current_hsv,
                    "message": message
                }
            except KasaException as e:
                message = f"Kasa Error for {target_ip} ({operation_name}): {str(e)}"
                print(f"[{operation_name}_op_for_{target_ip}] {message}")
                return {"ip_address": target_ip, "status": "error", "message": message}
            except asyncio.TimeoutError:
                message = f"Timeout during operation for {target_ip} ({operation_name})."
                print(f"[{operation_name}_op_for_{target_ip}] {message}")
                return {"ip_address": target_ip, "status": "error", "message": message}
            except Exception as e:
                message = f"Unexpected error for {target_ip} ({operation_name}): {type(e).__name__} - {str(e)}"
                print(f"[{operation_name}_op_for_{target_ip}] {message}")
                traceback.print_exc()
                return {"ip_address": target_ip, "status": "error", "message": message}

        print(f"\n[set_light_hsv] Initiating set HSV to ({hue},{saturation},{value}) for: {', '.join(ip_addresses_to_run_on)}")
        tasks_to_run = [_execute_set_hsv_for_ip(ip, hue, saturation, value) for ip in ip_addresses_to_run_on]
        results = await asyncio.gather(*tasks_to_run)
        print(f"[set_light_hsv] Completed set HSV operations.")
        return results
    finally:
        clear_tool_status()

@function_tool
async def get_light_state() -> list[dict]:
    """
    Gets the current state of the lights (on/off, HSV, brightness).
    Includes dev.update() to ensure properties are populated.
    """
    mark_checking_status()
    try:
        ip_addresses_to_run_on = [FIRST_IP_ADDRESS, SECOND_IP_ADDRESS]

        async def _execute_get_state_for_ip(target_ip: str) -> dict:
            is_on_state = "N/A"
            hsv_state = "N/A"
            brightness_state = "N/A"

            try:
                print(f"\n[get_light_state_op_for_{target_ip}] Attempting to discover device...")
                dev = await Discover.discover_single(target_ip, timeout=10)
                
                if dev is None:
                    print(f"[get_light_state_op_for_{target_ip}] Device not found (discover_single returned None).")
                    return {
                        "ip_address": target_ip, "status": "error",
                        "message": f"Device not found at {target_ip} (get_state)."
                    }

                print(f"[get_light_state_op_for_{target_ip}] Device discovered. Attempting to update device state...")
                await dev.update()
                print(f"[get_light_state_op_for_{target_ip}] Device state update complete.")

                try:
                    is_on_state = dev.is_on
                except AttributeError:
                    print(f"[get_light_state_op_for_{target_ip}] Device has no 'is_on' attribute after update.")
                    is_on_state = "N/A (is_on attribute missing)"

                try:
                    if not hasattr(dev, 'modules') or dev.modules is None:
                        print(f"[get_light_state_op_for_{target_ip}] Device 'modules' attribute is missing or is None after update.")
                        hsv_state = "N/A (modules unavailable)"
                        brightness_state = "N/A (modules unavailable)"
                    else:
                        light_module = dev.modules.get(Module.Light)
                        if light_module is None:
                            print(f"[get_light_state_op_for_{target_ip}] Light module (Module.Light) not found in dev.modules or is None after update.")
                            hsv_state = "N/A (light module missing)"
                            brightness_state = "N/A (light module missing)"
                        else:
                            try:
                                hsv_state = light_module.hsv
                            except AttributeError:
                                print(f"[get_light_state_op_for_{target_ip}] Light module has no 'hsv' attribute.")
                                hsv_state = "N/A (hsv not supported)"
                            try:
                                brightness_state = light_module.brightness
                            except AttributeError:
                                print(f"[get_light_state_op_for_{target_ip}] Light module has no 'brightness' attribute.")
                                brightness_state = "N/A (brightness not supported)"
                
                except KeyError as e_key:
                    print(f"[get_light_state_op_for_{target_ip}] Key error accessing module details after update: {e_key}")
                    hsv_state = "N/A (module key error)"
                    brightness_state = "N/A (module key error)"
                except AttributeError as e_attr_modules:
                    print(f"[get_light_state_op_for_{target_ip}] Attribute error with dev.modules structure after update: {e_attr_modules}")
                    hsv_state = "N/A (modules attribute error)"
                    brightness_state = "N/A (modules attribute error)"

                print(f"[get_light_state_op_for_{target_ip}] Device state: On={is_on_state}, HSV={hsv_state}, Brightness={brightness_state}")
                return {
                    "ip_address": target_ip, "status": "success",
                    "data": {"is_on": is_on_state, "hsv": hsv_state, "brightness": brightness_state},
                    "message": f"Successfully retrieved state for {target_ip}."
                }
            
            except KasaException as e:
                print(f"[get_light_state_op_for_{target_ip}] Kasa Error: {e}")
                return {"ip_address": target_ip, "status": "error", "message": f"Kasa Error for {target_ip} (get_state): {str(e)}"}
            except asyncio.TimeoutError as timeout_error:
                print(f"[get_light_state_op_for_{target_ip}] Timeout (discovery or update): {timeout_error}")
                return {"ip_address": target_ip, "status": "error", "message": f"Timeout for {target_ip} (get_state)."}
            except AttributeError as e: 
                print(f"[get_light_state_op_for_{target_ip}] General AttributeError: {e}")
                return {"ip_address": target_ip, "status": "error", "message": f"General AttributeError for {target_ip} (get_state): {str(e)}"}
            except Exception as e:
                print(f"[get_light_state_op_for_{target_ip}] Unexpected error: {e} ({type(e).__name__})")
                return {"ip_address": target_ip, "status": "error", "message": f"Unexpected error ({type(e).__name__}) for {target_ip} (get_state): {str(e)}"}

        print(f"\n[get_light_state] Initiating state retrieval for: {', '.join(ip_addresses_to_run_on)}")
        tasks_to_run = [_execute_get_state_for_ip(ip) for ip in ip_addresses_to_run_on]
        results = await asyncio.gather(*tasks_to_run)
        print(f"[get_light_state] Completed state retrieval operations.")
        return results
    finally:
        clear_tool_status()
