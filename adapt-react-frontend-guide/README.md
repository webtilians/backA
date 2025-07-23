# Hotel AselvIA - Adapt React Frontend Guide

## Overview

This guide provides instructions for adapting the React frontend chat application to the new changes in the backend project for the Hotel AselvIA system. It outlines the necessary updates to the socket connection, message handling, and tool usage based on the new backend functionalities.

## Instructions for Adapting the React Frontend Chat Application

1. **Update Socket Connection**:
   - Ensure that the socket connection URL points to the correct backend server. This can be done by setting the `REACT_APP_SOCKET_URL` environment variable in your `.env` file or directly in the code.
   - Example: 
     ```javascript
     const url = process.env.REACT_APP_SOCKET_URL || "http://localhost:8000";
     ```

2. **Handle New Events**:
   - The backend may have introduced new events or modified existing ones. Make sure to listen for any new events emitted by the backend, such as `bot-typing` or `tool-used`.
   - Update the event listeners in the `useEffect` hook to handle these events appropriately.

3. **Update Tool Usage Logic**:
   - Modify the logic in the `tool-used` event handler to reflect any new tools or changes in how tools are used. Ensure that the messages displayed to the user are clear and informative.
   - Example:
     ```javascript
     socketRef.current.on("tool-used", (data) => {
       if (data.tool) {
         setToolInUse(data.tool);
         setMessages((prev) => [
           ...prev,
           {
             sender: "tool",
             text: `🛠️ Usando la herramienta: ${toolLabel(data.tool)}...`
           }
         ]);
       }
     });
     ```

4. **Update Message Sending Logic**:
   - Ensure that the message format sent to the backend matches the expected structure. This may include sending additional context or history if required by the new backend implementation.
   - Example:
     ```javascript
     socketRef.current.emit("user_message", { mensaje: text, historial });
     ```

5. **Test the Integration**:
   - After making the necessary changes, thoroughly test the chat application to ensure that it interacts correctly with the backend. Check for any errors in the console and verify that all functionalities work as expected.

6. **Documentation**:
   - Update the `README.md` file to reflect any changes made to the frontend application, including new features, usage instructions, and any dependencies that may have changed.

By following these steps, you can successfully adapt the React frontend chat application to work with the updated backend for the Hotel AselvIA system.