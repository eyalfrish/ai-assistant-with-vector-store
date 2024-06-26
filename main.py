"""
The AI Assistant is an intelligent conversational tool leveraging the power of
OpenAI's GPT models to provide insightful and interactive responses. Built with
Langchain for advanced agent management, memory handling, and tool creation,
the assistant offers a seamless user experience through a Streamlit-based interface.

For more information, please check README.md
"""

# built-ins
import tempfile
import time
from pathlib import Path

# 3rd-party
import streamlit as st
from langchain.agents import AgentExecutor, ConversationalAgent
from langchain.memory import ConversationBufferWindowMemory
from langchain.tools.retriever import create_retriever_tool
from langchain_community.chat_message_histories.streamlit import (
    StreamlitChatMessageHistory,
)
from langchain_community.vectorstores.faiss import FAISS
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

# local
from utils.langchain_loaders import DocumentLoader


@st.cache_resource
def upload_tmp_dir() -> Path:
    """
    Creates a temporary directory and caches its Path for the Streamlit app's lifecycle.
    This is achieved by using the `@st.cache_resource` decorator.

    Returns:
        Path: Path to the created temporary directory.
    """
    return Path(tempfile.mkdtemp())


# Set page title
st.set_page_config(page_title="AI Assistant")

# Streamlit UI setup
st.title("AI Assistant")
st.caption("A powerful AI assistant powered by OpenAI")

# Sidebar setup
with st.sidebar:
    st.markdown(
        "# How to use\n"
        "Enter your [OpenAI API key](https://platform.openai.com/account/api-keys) below:"
    )
    openai_api_key = st.text_input("OpenAI API Key", type="password")

    st.markdown("Choose OpenAI model:")
    model_name = st.selectbox(
        "Model", options=["gpt-3.5-turbo", "gpt-4-turbo-preview", "gpt-4"]
    )
    temperature = st.slider(
        "Temperature", min_value=0.0, max_value=1.0, step=0.1, value=0.2
    )

    st.markdown("\n")
    st.markdown("Clear chat history:")
    clear_history = st.button("Clear History")

    st.markdown("---")
    st.markdown("# Upload a file")
    uploaded_files = st.file_uploader(
        label="Support vector store capabilities based on uploaded files.",
        type=DocumentLoader.supported_doc_extensions(),
        accept_multiple_files=True,
    )

    st.markdown("---")
    st.markdown("# About")
    st.markdown(
        """
        This AI assistant is based on OpenAI and is designed to answer questions based on its
        training knowledge.

        Additionally, it features a document upload capability using a vector store.

        Please note that this is a beta tool, and any feedback is appreciated to enhance its
        performance.
        """
    )
    st.markdown(
        "Made by [Sharon M.](https://www.linkedin.com/in/sharon-mordechai-a294b6129/)"
    )


# Validate OpenAI API key
if not openai_api_key:
    st.error("Please input your OpenAI API key in the sidebar.")
    st.stop()

# Initialize OpenAI agent
llm = ChatOpenAI(
    model_name=model_name, openai_api_key=openai_api_key, temperature=temperature
)
embeddings = OpenAIEmbeddings(openai_api_key=openai_api_key)

# Initialize chat history and memory
msgs = StreamlitChatMessageHistory()
memory = ConversationBufferWindowMemory(
    chat_memory=msgs,
    return_messages=True,
    memory_key="chat_history",
    output_key="output",
)

# Handle chat history clearing
if clear_history:
    st.session_state.messages = []

# Initialize session state variables
if "files" not in st.session_state:
    st.session_state.files = []
if "loader" not in st.session_state:
    st.session_state.loader = DocumentLoader()
if "on_change" not in st.session_state:
    st.session_state.on_change = False
if "messages" not in st.session_state:
    st.session_state.messages = []
if "agent" not in st.session_state:
    st.session_state.agent = AgentExecutor.from_agent_and_tools(
        agent=ConversationalAgent.from_llm_and_tools(llm=llm, tools=[]),
        tools=[],
        memory=memory,
        handle_parsing_errors=lambda error: str(error)[:50],
    )

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Handle file uploads
for file in uploaded_files:
    if file not in st.session_state.files:
        # Add file to the session files
        st.session_state.files.append(file)

        # Create temporary file path
        temp_filepath = upload_tmp_dir() / file.name

        # Save temporary file
        with temp_filepath.open("wb") as temp_file:
            temp_file.write(file.getvalue())

        # Load document
        st.session_state.loader.load(temp_filepath)

        # Set on_change to True to initialize the vector store
        st.session_state.on_change = True

# Handle file removals
for file in st.session_state.files:
    if file not in uploaded_files:
        # Create temporary file path
        temp_filepath = upload_tmp_dir() / file.name

        # Remove this file from the session loader
        st.session_state.loader.remove(temp_filepath)

        # Remove temporary file
        temp_filepath.unlink()

        # Remove this file from the session files
        st.session_state.files.remove(file)

        # Set on_change to True to initialize the vector store
        st.session_state.on_change = True

# Update vector store if there are changes in files
if st.session_state.on_change:
    with st.spinner("Uploading files..."):
        if st.session_state.loader.size > 0:
            # Split documents
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=1500, chunk_overlap=200
            )
            documents = text_splitter.split_documents(st.session_state.loader.documents)

            # Create a vector store
            vector = FAISS.from_documents(documents, embeddings)

            # Create a vector tool for agent
            FILENAME_STR = ", ".join(
                [file.name.split(".")[0] for file in uploaded_files]
            )
            vector_tool = create_retriever_tool(
                retriever=vector.as_retriever(),
                name="vector-tool",
                description=f"Useful for searching information about {FILENAME_STR}",
            )

            # Initialize agent with the vector tool
            st.session_state.agent = AgentExecutor.from_agent_and_tools(
                agent=ConversationalAgent.from_llm_and_tools(
                    llm=llm, tools=[vector_tool]
                ),
                tools=[vector_tool],
                memory=memory,
                handle_parsing_errors=lambda error: str(error)[:50],
            )
        else:
            # Initialize agent without the vector tool
            st.session_state.agent = AgentExecutor.from_agent_and_tools(
                agent=ConversationalAgent.from_llm_and_tools(llm=llm, tools=[]),
                tools=[],
                memory=memory,
                handle_parsing_errors=lambda error: str(error)[:50],
            )
    st.session_state.on_change = False
    st.toast("Files were updated successfully.")


# Function to stream the response for a more interactive chat experience
def stream_response(res):
    """Stream the response for a more interactive chat experience."""
    for word in res.split(" "):
        yield word + " "
        time.sleep(0.02)


# The following appears also in the examples/streamlit_open_ai.py file
# For now, we disable pylint's check for similar code in different files
# pylint: disable=R0801

# Handle user input and generate response
if prompt := st.chat_input("Type your message here..."):
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        stream_res = stream_response(st.session_state.agent.invoke(prompt)["output"])
        response = st.write_stream(stream_res)

    st.session_state.messages.append({"role": "assistant", "content": response})
