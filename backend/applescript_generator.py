import re
import subprocess
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# --- Custom Exceptions ---
class AppleScriptExtractionError(Exception):
    """Raised when the markdown wrapper is missing or malformed."""
    pass

class AppleScriptSyntaxError(Exception):
    """Raised when the AppleScript fails syntax compilation."""
    pass


# --- Helper Functions ---
def extract_applescript(text: str) -> str:
    """
    Extracts AppleScript from markdown code blocks.
    Raises AppleScriptExtractionError if the extremes are not found.
    """
    # Regex to capture everything between ```applescript and ```
    match = re.search(r'```applescript\s*(.*?)\s*```', text, re.DOTALL | re.IGNORECASE)
    
    if match:
        return match.group(1).strip()
    
    # Check if a generic markdown block was used instead
    if re.search(r'```\s*(.*?)\s*```', text, re.DOTALL):
        raise AppleScriptExtractionError(
            "Markdown code block found, but the 'applescript' language identifier is missing."
        )
        
    raise AppleScriptExtractionError(
        "Failed to find the required markdown code block markers (```applescript ... ```)."
    )


def verify_applescript_syntax(script_content: str):
    """
    Verifies the AppleScript syntax using the macOS 'osacompile' utility.
    Raises AppleScriptSyntaxError if the compilation fails.
    """
    try:
        # -o /dev/null compiles the script to check syntax without creating an output file
        # -e executes/compiles the inline script provided
        result = subprocess.run(
            ['osacompile', '-o', '/dev/null', '-e', script_content],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            # osacompile outputs syntax errors to stderr
            error_msg = result.stderr.strip() or "Unknown syntax error during compilation."
            raise AppleScriptSyntaxError(f"AppleScript Syntax Error:\n{error_msg}")
            
    except FileNotFoundError:
        # Handles the case where this script is run on a non-macOS environment
        print("Warning: 'osacompile' utility not found. Skipping syntax verification (requires macOS).")


# --- Main LangChain Execution & Retry System ---
def generate_and_verify_applescript(user_query: str, max_retries: int = 2) -> str:
    """
    Generates an AppleScript using an LLM, verifies it, and retries upon failure.
    """
    llm = ChatOpenAI(
        base_url="http://localhost:11434/v1",
        api_key="ollama",
        model="gemma4:26b",
        temperature=0.1
    )

    system_instruction = (
        "You are an AppleScript expert. "
        "Write the AppleScript to satisfy the user's request. "
        "You MUST wrap your output script in markdown code syntax exactly like this:\n"
        "```applescript\n<your script here>\n```"
    )

    # Base LCEL Chain for the first attempt
    base_prompt = ChatPromptTemplate.from_messages([
        ("system", system_instruction),
        ("user", "{input}")
    ])
    base_chain = base_prompt | llm | StrOutputParser()

    # Retry LCEL Chain for fixing errors
    retry_prompt = ChatPromptTemplate.from_messages([
        ("system", system_instruction),
        ("user", "Task: {input}\n\n"
                 "Your previous output:\n{previous_output}\n\n"
                 "Resulted in this error during verification:\n{error_message}\n\n"
                 "Please fix the error and try again, ensuring the output is properly wrapped.")
    ])
    retry_chain = retry_prompt | llm | StrOutputParser()

    previous_output = ""
    error_message = ""
    
    # Total attempts = 1 initial attempt + max_retries
    total_attempts = 1 + max_retries 

    for attempt in range(total_attempts):
        print(f"Attempt {attempt + 1} of {total_attempts}...")
        
        # 1. Generate Output
        if attempt == 0:
            raw_output = base_chain.invoke({"input": user_query})
        else:
            raw_output = retry_chain.invoke({
                "input": user_query,
                "previous_output": previous_output,
                "error_message": error_message
            })
            
        # Store the exact LLM output so we can feed it back if it fails again
        previous_output = raw_output 
        
        try:
            # 2. Extract
            script = extract_applescript(raw_output)
            
            # 3. Verify
            verify_applescript_syntax(script)
            
            # If no exceptions are raised, the script is valid!
            print("Verification successful!")
            return script
            
        except (AppleScriptExtractionError, AppleScriptSyntaxError) as e:
            error_message = str(e)
            print(f"Error encountered: {error_message}\n")
            
    print("Maximum retry attempts reached. Giving up.")
    return None

# --- Example Usage ---
if __name__ == "__main__":
    # Deliberately asking for a syntax error to test the retry loop
    task = "Create a notification that says 'Hello World'." 
    
    final_script = generate_and_verify_applescript(task)
    
    if final_script:
        print("\n--- Final Valid AppleScript ---")
        print(final_script)
    else:
        print("\n--- Failed to generate valid script ---")