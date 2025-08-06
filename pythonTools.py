import io
import sys
import traceback
from contextlib import redirect_stdout, redirect_stderr
from rich.console import Console
from RestrictedPython import compile_restricted, safe_globals, limited_builtins, utility_builtins
from RestrictedPython.PrintCollector import PrintCollector
from agents import function_tool

console = Console()

def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    """Safe import function that allows common modules."""
    allowed_modules = {
        'math', 'random', 'json', 'datetime', 'time', 'collections',
        're', 'itertools', 'functools', 'operator', 'string', 'decimal',
        'fractions', 'statistics', 'uuid', 'hashlib', 'base64', 'binascii',
        'sympy'
    }
   
    if name in allowed_modules or name.split('.')[0] in allowed_modules:
        return __import__(name, globals, locals, fromlist, level)
    else:
        raise ImportError(f"Module '{name}' is not allowed in restricted mode")

namespace = {
    '__builtins__': limited_builtins.copy(),
    **safe_globals,
    **utility_builtins,
    '_print_': PrintCollector,
    '_getattr_': getattr,
    '_getitem_': lambda obj, key: obj[key],
    '_getiter_': iter,
    '_iter_unpack_sequence_': lambda it, spec: list(it),
    'sympy': __import__('sympy')
}

namespace['__builtins__']['__import__'] = safe_import

namespace['__builtins__'].update({
    'sum': sum,
    'max': max,
    'min': min,
    'list': list,
    'dict': dict,
    'set': set,
    'enumerate': enumerate,
    'reversed': reversed,
    'all': all,
    'any': any,
    'filter': filter,
    'map': map,
})

@function_tool
def execute_python(code: str):
    """Execute Python code in a restricted sandbox and return the output.
    
    This tool allows running custom Python scripts for computations, data analysis, etc.
    It maintains state across calls (REPL-style), so variables persist.
    
    Args:
        code (str): The Python code to execute.
    
    Returns:
        str: The execution output, including stdout, stderr, and any results or errors.
    """
    console.print(f"\nExecuting Python code:\n{code}", style="dim blue")
    
    if code.strip() == "debug_namespace":
        return f"Namespace keys: {list(namespace.keys())}\n__builtins__ keys: {list(namespace['__builtins__'].keys())}"
    
    try:
        previous_result = namespace.get('result', '<NOT_SET>')
        
        byte_code = compile_restricted(code, '<string>', 'exec')
        
        if byte_code is None:
            return "Compilation failed: RestrictedPython rejected the code"
        
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        
        try:
            sys.stdout = stdout_capture
            sys.stderr = stderr_capture
            
            exec(byte_code, namespace, namespace)
            
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
        
        output = stdout_capture.getvalue().strip()
        error = stderr_capture.getvalue().strip()
        
        print_output = ""
        if '_print' in namespace and hasattr(namespace['_print'], 'txt'):
            if isinstance(namespace['_print'].txt, list):
                print_output = ''.join(str(item) for item in namespace['_print'].txt).strip()
            else:
                print_output = str(namespace['_print'].txt).strip()
            namespace['_print'] = PrintCollector()
        
        result_parts = []
        
        if print_output:
            result_parts.append(f"Print Output:\n{print_output}")
        
        if output:
            result_parts.append(f"Stdout:\n{output}")
            
        if error:
            result_parts.append(f"Stderr:\n{error}")
        
        current_result = namespace.get('result', '<NOT_SET>')
        if 'result' in namespace and (current_result != previous_result or 'result' in code):
            result_parts.append(f"Result: {namespace['result']}")
        
        if result_parts:
            return "\n".join(result_parts)
        else:
            return "Execution completed successfully (no output)."
    
    except Exception as e:
        tb = traceback.format_exc()
        return f"Execution failed: {str(e)}\nTraceback:\n{tb}"