'''
Run generated code in a sandbox environment.
'''

from typing import Generator, TypedDict
import gradio as gr
import re
import os
import base64
from e2b import Sandbox
from e2b_code_interpreter import Sandbox as CodeSandbox
from gradio_sandboxcomponent import SandboxComponent

E2B_API_KEY = os.environ.get("E2B_API_KEY")
'''
API key for the e2b API.
'''

SUPPORTED_SANDBOX_ENVIRONMENTS = [
    # TODO: Support Code Interpreter
    # 'Python',
    # 'Java',
    # 'Javascript',
    'React',
    'Vue',
    'Gradio',
    'Streamlit',
    'NiceGUI',
    'PyGame',
    # 'Auto' # TODO: Implement auto-detection of sandbox environment
]

VALID_GRADIO_CODE_LANGUAGES = ['python', 'c', 'cpp', 'markdown', 'json', 'html', 'css', 'javascript', 'jinja2', 'typescript', 'yaml', 'dockerfile', 'shell', 'r', 'sql',
                               'sql-msSQL', 'sql-mySQL', 'sql-mariaDB', 'sql-sqlite', 'sql-cassandra', 'sql-plSQL', 'sql-hive', 'sql-pgSQL', 'sql-gql', 'sql-gpSQL', 'sql-sparkSQL', 'sql-esper']
'''
Languages that gradio code component can render.
'''

RUN_CODE_BUTTON_HTML = "<button style='background-color: #4CAF50; border: none; color: white; padding: 10px 24px; text-align: center; text-decoration: none; display: inline-block; font-size: 16px; margin: 4px 2px; cursor: pointer; border-radius: 12px;'>Click to Run in Sandbox</button>"
'''
Button in the chat to run the code in the sandbox.
'''

SANDBOX_CODE_TAG = "***REMOTE SANDBOX CODE:***"

GENERAL_SANDBOX_INSTRUCTION = """ Generate code for a single file to be executed in a sandbox. You can output other information if needed. The code should be in the markdown format:
***REMOTE SANDBOX CODE:***
```<language>
<code>
```
"""

DEFAULT_REACT_SANDBOX_INSTRUCTION = """ Generate typescript for a single-file Next.js 13+ React component tsx file. . Do not use external libs or import external files. Allowed libs: ["nextjs@14.2.5", "typescript", "@types/node", "@types/react", "@types/react-dom", "postcss", "tailwindcss", "shadcn"] """
'''
Default sandbox prompt instruction.
'''

DEFAULT_VUE_SANDBOX_INSTRUCTION = """ Generate TypeScript for a single-file Vue.js 3+ component (SFC) in .vue format. The component should be a simple custom page in a styled `<div>` element. Do not include <NuxtWelcome /> or reference any external components. Surround the code with ``` in markdown. Do not use external libraries or import external files. Allowed libs: ["nextjs@14.2.5", "typescript", "@types/node", "@types/react", "@types/react-dom", "postcss", "tailwindcss", "shadcn"], """
'''
Default sandbox prompt instruction for vue.
'''

DEFAULT_PYGAME_SANDBOX_INSTRUCTION = (
'''
Generate a pygame code snippet for a single file.
Write pygame main method in a sync function like:
```python
import asyncio
import pygame

async def main():
    global game_state
    while game_state:
        game_state(pygame.event.get())
        pygame.display.update()
        await asyncio.sleep(0) # it must be called on every frame

if __name__ == "__main__":
    asyncio.run(main())
```
'''
)

DEFAULT_GRADIO_SANDBOX_INSTRUCTION = """
Generate Python code for a single-file Gradio application using the Gradio library.
Do not use external libraries or import external files outside of the allowed list.
Allowed libraries: ["gradio", "pandas", "numpy", "matplotlib", "requests", "seaborn", "plotly"]
"""

DEFAULT_NICEGUI_SANDBOX_INSTRUCTION = """
Generate a Python NiceGUI code snippet for a single file.
"""

DEFAULT_STREAMLIT_SANDBOX_INSTRUCTION = """
Generate Python code for a single-file Streamlit application using the Streamlit library.
The app should automatically reload when changes are made. 
Do not use external libraries or import external files outside of the allowed list.
Allowed libraries: ["streamlit", "pandas", "numpy", "matplotlib", "requests", "seaborn", "plotly"]
"""

DEFAULT_SANDBOX_INSTRUCTIONS = {
    # "Auto": "Auto-detect the code language and run in the appropriate sandbox.",
    "React": GENERAL_SANDBOX_INSTRUCTION + DEFAULT_REACT_SANDBOX_INSTRUCTION.strip(),
    "Vue": GENERAL_SANDBOX_INSTRUCTION + DEFAULT_VUE_SANDBOX_INSTRUCTION.strip(),
    "Gradio": GENERAL_SANDBOX_INSTRUCTION + DEFAULT_GRADIO_SANDBOX_INSTRUCTION.strip(),
    "Streamlit": GENERAL_SANDBOX_INSTRUCTION + DEFAULT_STREAMLIT_SANDBOX_INSTRUCTION.strip(),
    "NiceGUI": GENERAL_SANDBOX_INSTRUCTION + DEFAULT_NICEGUI_SANDBOX_INSTRUCTION.strip(),
    "PyGame": GENERAL_SANDBOX_INSTRUCTION +DEFAULT_PYGAME_SANDBOX_INSTRUCTION.strip(),
}

class ChatbotSandboxState(TypedDict):
    '''
    Chatbot sandbox state in gr.state.
    '''
    enable_sandbox: bool
    sandbox_environment: str | None
    sandbox_instruction: str | None
    enabled_round: int


def create_chatbot_sandbox_state() -> ChatbotSandboxState:
    '''
    Create a new chatbot sandbox state.
    '''
    return {
        "enable_sandbox": False,
        "sandbox_environment": None,
        "sandbox_instruction": None,
        "enabled_round": 0
    }


def update_sandbox_config(
    enable_sandbox: bool,
    sandbox_environment: str,
    sandbox_instruction: str,
    *states: ChatbotSandboxState
) -> list[ChatbotSandboxState]:
    '''
    Fn to update sandbox config.
    '''
    for state in states:
        state["enable_sandbox"] = enable_sandbox
        state["sandbox_instruction"] = sandbox_instruction
        state["sandbox_environment"] = sandbox_environment
    return list(states)

def update_sandbox_config_single_model(
    enable_sandbox: bool,
    sandbox_environment: str,
    sandbox_instruction: str,
    state: ChatbotSandboxState
) -> ChatbotSandboxState:
    '''
    Fn to update sandbox config for single model.
    '''
    state["enable_sandbox"] = enable_sandbox
    state["sandbox_instruction"] = sandbox_instruction
    state["sandbox_environment"] = sandbox_environment

    return state

def extract_code_from_markdown(message: str) -> tuple[str, str, bool] | None:
    '''
    Extracts code from a markdown message.

    Returns:
        tuple[str, str, bool]: A tuple containing the code, code language, and a boolean indicating whether the code is a webpage.
    '''
    # Regular expression to match code blocks with optional language
    code_block_regexes = [
        rf'{re.escape(SANDBOX_CODE_TAG)}\s*```(\w+)?\n(.*?)```',
        r'```(\w+)?\n(.*?)```'
    ]
    for code_block_regex in code_block_regexes:
        matches = re.findall(code_block_regex, message, re.DOTALL)
        if matches:
            break

    if matches:
        # Extract code language and code
        code_lang = matches[0][0] or ''
        code = matches[0][1].strip()
    else:
        # if no code block is found, return None
        return None

    # Determine if the code is related to a webpage
    if any(word in message.lower() for word in ['typescript', 'javascript', 'react','vue','gradio','streamlit']):
        is_webpage = True
    else:
        is_webpage = False

    return code, code_lang, is_webpage


def render_result(result):
    if result.png:
        if isinstance(result.png, str):
            img_str = result.png
        else:
            img_str = base64.b64encode(result.png).decode()
        return f"<img src='data:image/png;base64,{img_str}'>"
    elif result.jpeg:
        if isinstance(result.jpeg, str):
            img_str = result.jpeg
        else:
            img_str = base64.b64encode(result.jpeg).decode()
        return f"<img src='data:image/jpeg;base64,{img_str}'>"
    elif result.svg:
        return result.svg
    elif result.html:
        return result.html
    elif result.markdown:
        return f"```markdown\n{result.markdown}\n```"
    elif result.latex:
        return f"```latex\n{result.latex}\n```"
    elif result.json:
        return f"```json\n{result.json}\n```"
    elif result.javascript:
        return result.javascript  # Return raw JavaScript
    else:
        return str(result)


def run_code_interpreter(code: str, code_language: str | None) -> tuple[str, str, str]:
    """
    Executes the provided code within a sandboxed environment and returns the output.

    Args:
        code (str): The code to be executed.

    Returns:
        tuple[str, str, str]: A tuple containing the standard output, rendered results, and JavaScript code.
    """
    with CodeSandbox() as sandbox:
        execution = sandbox.run_code(
            code=code,
            language=code_language
        )

        # collect stdout, stderr from sandbox
        stdout = "\n".join(execution.logs.stdout)
        stderr = "\n".join(execution.logs.stderr)
        output = ""
        if stdout:
            output += f"### Stdout:\n```\n{stdout}\n```\n\n"
        if stderr:
            output += f"### Stderr:\n```\n{stderr}\n```\n\n"

        results = []
        js_code = ""
        for result in execution.results:
            rendered_result = render_result(result)
            if result.javascript:
                js_code += rendered_result + "\n"
            else:
                results.append(rendered_result)
        return output, "\n".join(results), js_code

def run_react_sandbox(code: str) -> str:
    """
    Executes the provided code within a sandboxed environment and returns the output.

    Args:
        code (str): The code to be executed.

    Returns:
        url for remote sandbox
    """
    sandbox = Sandbox(
        template="nextjs-developer",
        metadata={
            "template": "nextjs-developer"
        },
        api_key=E2B_API_KEY,
    )

    # set up the sandbox
    sandbox.files.make_dir('pages')
    file_path = "~/pages/index.tsx"
    sandbox.files.write(path=file_path, data=code, request_timeout=60)

    # get the sandbox url
    sandbox_url = 'https://' + sandbox.get_host(3000)
    return sandbox_url

def run_vue_sandbox(code: str) -> str:
    """
    Executes the provided Vue code within a sandboxed environment and returns the output.

    Args:
        code (str): The Vue code to be executed.

    Returns:
        url for remote sandbox
    """
    sandbox = Sandbox(
        template="vue-developer",
        metadata={
            "template": "vue-developer"
        },
        api_key=E2B_API_KEY,
    )

    # Set up the sandbox
    file_path = "~/app.vue"
    sandbox.files.write(path=file_path, data=code, request_timeout=60)

    # Get the sandbox URL
    sandbox_url = 'https://' + sandbox.get_host(3000) 
    return sandbox_url

def run_pygame_sandbox(code: str) -> str:
    """
    Executes the provided code within a sandboxed environment and returns the output.

    Args:
        code (str): The code to be executed.

    Returns:
        url for remote sandbox
    """
    sandbox = Sandbox(
        api_key=E2B_API_KEY,
    )

    sandbox.files.make_dir('mygame')
    file_path = "~/mygame/main.py"
    sandbox.files.write(path=file_path, data=code, request_timeout=60)

    sandbox.commands.run("pip install pygame pygbag black",
                        timeout=60 * 3,
                        # on_stdout=lambda message: print(message),
                        on_stderr=lambda message: print(message),)

    # build the pygame code
    sandbox.commands.run(
        "pygbag --build ~/mygame", # build game
        timeout=60 * 5,
        # on_stdout=lambda message: print(message),
        # on_stderr=lambda message: print(message),
    )

    process = sandbox.commands.run("python -m http.server 3000", background=True) # start http server

    # get game server url
    host = sandbox.get_host(3000)
    url = f"https://{host}"
    return url + '/mygame/build/web/'

def run_nicegui_sandbox(code: str) -> str:
    """
    Executes the provided code within a sandboxed environment and returns the output.

    Args:
        code (str): The code to be executed.

    Returns:
        url for remote sandbox
    """
    sandbox = Sandbox(
        api_key=E2B_API_KEY,
    )

    # set up sandbox
    setup_commands = [
        "pip install --upgrade nicegui",
    ]
    for command in setup_commands:
        sandbox.commands.run(
            command,
            timeout=60 * 3,
            on_stdout=lambda message: print(message),
            on_stderr=lambda message: print(message),
        )

    # write code to file
    sandbox.files.make_dir('mynicegui')
    file_path = "~/mynicegui/main.py"
    sandbox.files.write(path=file_path, data=code, request_timeout=60)

    process = sandbox.commands.run("python ~/mynicegui/main.py", background=True)

    # get web gui url
    host = sandbox.get_host(port=8080)
    url = f"https://{host}"
    return url

def run_gradio_sandbox(code: str) -> str:
    """
    Executes the provided code within a sandboxed environment and returns the output.

    Args:
        code (str): The code to be executed.

    Returns:
        url for remote sandbox
    """
    sandbox = Sandbox(
        template="gradio-developer",
        metadata={
            "template": "gradio-developer"
        },
        api_key=E2B_API_KEY,
    )

    # set up the sandbox
    file_path = "~/app.py"
    sandbox.files.write(path=file_path, data=code, request_timeout=60)

    # get the sandbox url
    sandbox_url = 'https://' + sandbox.get_host(7860)
    return sandbox_url

def run_streamlit_sandbox(code: str) -> str:
    sandbox = Sandbox(api_key=E2B_API_KEY)

    setup_commands = ["pip install --upgrade streamlit"]
                    
    for command in setup_commands:
        sandbox.commands.run(
            command,
            timeout=60 * 3,
            on_stdout=lambda message: print(message),
            on_stderr=lambda message: print(message),
        )
  
    sandbox.files.make_dir('mystreamlit')
    file_path = "~/mystreamlit/app.py"
    sandbox.files.write(path=file_path, data=code, request_timeout=60)
    
    process = sandbox.commands.run(
        "streamlit run ~/mystreamlit/app.py --server.port 8501 --server.headless true", 
        background=True
    )
    
    host = sandbox.get_host(port=8501)
    url = f"https://{host}"
    return url

def on_click_run_code(
        state,
        sandbox_state: ChatbotSandboxState,
        sandbox_output: gr.Markdown,
        sandbox_ui: SandboxComponent,
        sandbox_code: gr.Code,
        evt: gr.SelectData
    ):
    '''
    gradio fn when run code is clicked. Update Sandbox components.
    '''
    if sandbox_state['enable_sandbox'] is not True or not evt.value.endswith(RUN_CODE_BUTTON_HTML):
        return None, None, None

    message = evt.value.replace(RUN_CODE_BUTTON_HTML, "").strip()

    extract_result = extract_code_from_markdown(message)
    if extract_result is None:
        return gr.skip(), gr.skip(), gr.skip()

    # validate e2b api key
    if not E2B_API_KEY:
        raise ValueError("E2B_API_KEY is not set in env vars.")

    code, code_language, is_web_page = extract_result
    if code_language == 'tsx':
        code_language = 'typescript'
    code_language = code_language.lower() if code_language and code_language.lower() in VALID_GRADIO_CODE_LANGUAGES else None # ensure gradio supports the code language

    # show loading
    yield (
        gr.Markdown(value="### Running Sandbox (Loading)", visible=True),
        gr.skip(),
        gr.Code(value=code, language=code_language, visible=True),
    )

    if sandbox_state['sandbox_environment'] == 'React':
        url = run_react_sandbox(code)
        yield (
            gr.Markdown(value="### Running Sandbox", visible=True),
            SandboxComponent(
                value=(url, code),
                label="Example",
                visible=True,
                key="newsandbox",
            ),
            gr.skip(),
        )
    elif sandbox_state['sandbox_environment'] == 'Vue':
        url = run_vue_sandbox(code)
        yield (
            gr.Markdown(value="### Running Sandbox", visible=True),
            SandboxComponent(
                value=(url, code),
                label="Example",
                visible=True,
                key="newsandbox",
            ),
            gr.skip(),
        )
    elif sandbox_state['sandbox_environment'] == 'PyGame':
        url = run_pygame_sandbox(code)
        yield (
            gr.Markdown(value="### Running Sandbox", visible=True),
            SandboxComponent(
                value=(url, code),
                label="Example",
                visible=True,
                key="newsandbox",
            ),
            gr.skip(),
        )
    elif sandbox_state['sandbox_environment'] == 'Gradio':
        url = run_gradio_sandbox(code)
        yield (
            gr.Markdown(value="### Running Sandbox", visible=True),
            SandboxComponent(
                value=(url, code),
                label="Example",
                visible=True,
                key="newsandbox",
            ),
            gr.skip(),
        )
    elif sandbox_state['sandbox_environment'] == 'Streamlit':
        url = run_streamlit_sandbox(code)
        yield (
            gr.Markdown(value="### Running Sandbox", visible=True),
            SandboxComponent(
                value=(url, code),
                label="Example",
                visible=True,
                key="newsandbox",
            ),
            gr.skip(),
        )
    elif sandbox_state['sandbox_environment'] == 'NiceGUI':
        url = run_nicegui_sandbox(code)
        yield (
            gr.Markdown(value="### Running Sandbox", visible=True),
            SandboxComponent(
                value=(url, code),
                label="Example",
                visible=True,
                key="newsandbox",
            ),
            gr.skip(),
        )
    else:
        output, results, js_code = run_code_interpreter(
            code=code, code_language=code_language)
        yield (
            gr.Markdown(value=output, visible=True),
            None,
            gr.skip()
        )