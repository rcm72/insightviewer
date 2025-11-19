// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2025 Robert Čmrlec

//indexScript.js
var gAllowedNodeLabels = [];  // Global variable to store allowed node labels
var gAllowedEdgeTypes = [];  // Global variable to store allowed edge types
var nodes = new vis.DataSet([]);  // Global variable
var edges = new vis.DataSet([]);  // Global variable
var network = null; 
var createNodeCurrentShape="ellipse"; // Default shape for new nodes
var gCustomGraphName = ""; // Global variable to store the custom graph name

// Map to store node IDs to node names
var nodeIdToNameMap = new Map();
let showProperties = false; // Global variable to control the dialog behavior
let isManualGraph = false; // Flag to indicate if the graph is manual
var options = {
    interaction: { 
        hover: true,
        tooltipDelay: 300, // Delay before showing the tooltip
        multiselect: false // Disable default right-click behavior
    },
    physics: {
        enabled: true,
        barnesHut: {
            gravitationalConstant: -8000,
            centralGravity: 0.55,
            springLength: 75,
            springConstant: 0.04,
            damping: 1.5,
            avoidOverlap: 0.2
        },
        adaptiveTimestep: true,
        stabilization: {
            iterations: 10
        }
    },
    edges: {
        arrows: {
            to: { enabled: true, scaleFactor: 1 } // Ensure arrows are enabled
        },
        color: { color: "#848484", highlight: "#848484", hover: "#848484" },
        font: { size: 12, align: "top" }
    },    
    manipulation: {
        enabled: true,
        addNode: function (data, callback) {
            // Store the node data and callback globally
            window.currentNodeData = data;
            window.currentCallback = callback;

            // Open the "Add Node" dialog
            openNodeDialog();
        },
        addEdge: function (data, callback) {
            try {
                console.log("Edge data:", data); // Debugging log

                if (data.from === undefined || data.from === null || data.to === undefined || data.to === null) {
                    console.error("Source or target node is missing!");
                    return;
                }

                // Store the edge data and callback globally
                window.currentEdgeData = data;
                window.currentCallback = callback;

                // Open the "Add Edge" dialog
                openEdgeDialog();
            } catch (error) {
                console.error("Error in addEdge:", error);
                alert("An error occurred while adding the edge.");
                callback(null); // Cancel the edge creation
            }
        },
        editNode: function (data, callback) {
            let newLabel = prompt("Enter new node label:", data.label);
            if (newLabel !== null) {
                // Send the updated label to the server
                fetch("/update-node", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ id: data.id, name: newLabel }) // Send node ID and new name
                })
                .then(response => response.json())
                .then(result => {
                    if (result.success) {
                        // Update the label in the graph
                        data.label = newLabel;
                        callback(data); // Notify Vis.js that the node was updated
                        console.log("Node updated successfully:", result);
                    } else {
                        alert("Error updating node: " + result.message);
                        callback(null); // Cancel the edit
                    }
                })
                .catch(error => {
                    console.error("Error updating node:", error);
                    alert("An error occurred while updating the node.");
                    callback(null); // Cancel the edit
                });
            } else {
                callback(null); // Cancel the edit if no new label is provided
            }
        },         
        editEdge: true,
        deleteNode: function (data, callback) {
            deleteSelected(); // Call the custom deleteSelected function
            callback(null); // Prevent the default behavior
        },
        deleteEdge: function (data, callback) {
            const selectedEdges = data.edges; // Get the selected edges

            if (selectedEdges.length === 0) {
                alert("No edges selected for deletion.");
                callback(null); // Cancel the deletion
                return;
            }

            // Confirm deletion
            if (!confirm("Are you sure you want to delete the selected connection ?")) {
                callback(null); // Cancel the deletion
                return;
            }

            console.log("Deleting edges:", selectedEdges);

            // Send the selected edges to the backend for deletion
            fetch("/delete-selected", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ edges: selectedEdges })
            })
            .then(response => response.json())
            .then(result => {
                if (result.success) {
                    // Remove edges from the frontend graph
                    edges.remove(selectedEdges);
                    alert("Selected connection(s) deleted successfully.");
                    callback(data); // Notify Vis.js that the edges were deleted
                } else {
                    alert("Error deleting connection(s): " + result.error);
                    callback(null); // Cancel the deletion
                }
            })
            .catch(error => {
                console.error("Error deleting connection(s):", error);
                alert("An error occurred while deleting the connection(s).");
                callback(null); // Cancel the deletion
            });
            console.log("Finish deleting edges:", selectedEdges);
        }
    }
};

function testAdd() {
    //Add a node of image type
    nodes.add({ id: 1, 
                label: "Node 1", 
                shape: "image", 
                image: "/static/images/deska.jpg", 
                size: 70,
                borderWidth: 2,
                color: {border: "#2B7CE9", background: "#97C2FC"},
                name: "Node 1"  // Custom property to store the name
              }
            );
}

async function getNodeTypeProperties(pNodeName) {
    try {
        const resp = await fetch("/nodes/get_node_type_property", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ nodeType: pNodeName })
        });

        // handle non-JSON responses gracefully
        const contentType = resp.headers.get("Content-Type") || "";
        const text = await resp.text();
        if (!contentType.toLowerCase().includes("application/json")) {
            console.error("Non-JSON response for getNodeTypeProperties:", text);
            return null;
        }

        const result = JSON.parse(text);
        if (result.success) {
            console.log(`Property of node type ${pNodeName}:`, result.properties || result.value || result);
            return result;
        } else {
            console.error("Error fetching node property:", result.error);
            return null;
        }
    } catch (error) {
        console.error("Error fetching node property:", error);
        return null;
    }
}

async function submitNode(shape) {
    //20250606
    isManualGraph = false; // Set the flag to indicate manual graph creation
    let nodeType = document.getElementById("node-type-selector").value;
    let nodeName = document.getElementById("node-name").value;
    let nodeImageField = document.getElementById("node-image-url").value;

    if (!nodeName) {
        alert("Please enter a node name.");
        return;
    }

    let data = {};

    // Optionally fetch node type properties (not required for node creation but available)
    const nodeTypeInfo = await getNodeTypeProperties(nodeType);  // now returns a Promise

    // proceed to create the node on the backend
    fetch("/add-node", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: nodeName, label: nodeType, nodeImageField: nodeImageField})
    })
    .then(response => response.json())
    .then(result => {
        if (result.success) {
            console.log("Submitting node with result.id:", result.node_id); // Debugging log
            data.id = result.node_id;
            data.label = nodeName;
            data.labels = result.labels; // Store labels in the node object

            // Fetch the node visuals from the backend
            fetch(`/nodes/get_node_type_visuals`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ nodeType: nodeType })
            })
            .then(response => response.json())
            .then(nodeVisuals => {
                if (nodeVisuals.success) {
                    // determine final shape (priority: backend visuals -> passed shape -> default)
                    const finalShape = nodeVisuals.shape || shape || createNodeCurrentShape || "ellipse";
                    data.shape = finalShape;
                    data.color = nodeVisuals.color || "#97C2FC";
                    data.properties = { ...nodeVisuals.properties, name: nodeName };

                    // If the node is an image type, pick up the user-specified image URL (if provided)
                    if (finalShape === "image" || finalShape === "circularImage") {
                        const urlInput = document.getElementById("node-image-url");
                        if (urlInput && urlInput.value.trim()) {
                            data.image = urlInput.value.trim();
                        } else if (nodeVisuals.image) {
                            // fallback to any image provided by the backend visuals
                            data.image = nodeVisuals.image;
                        }
                        // allow backend-provided size
                        if (nodeVisuals.size) data.size = nodeVisuals.size;
                    }

                    nodes.add(data); // Add node to dataset
                    refreshGraph();
                    console.log("Node added to dataset:", nodes.get(data.id));
                    nodeIdToNameMap.set(data.id, nodeName); // Store node ID to name mapping

                    if (typeof window.currentCallback === "function") {
                        window.currentCallback(data);
                    } else {
                        console.error("Callback function is missing!");
                    }
                } else {
                    console.error("Error fetching node visuals:", nodeVisuals.error);
                }
            })
            .catch(error => console.error("Error fetching node visuals:", error));
        } else {
            alert("Error adding node.");
        }
    })
    .catch(error => console.error("Error:", error));

    console.log("nodes:", { nodesContent : nodes.get() });
}

function submitEdge() {
    let edgeType = document.getElementById("edge-type-selector").value;
    let edgeName = document.getElementById("edge-name").value;

    if (!edgeName) {
        alert("Please enter an edge name.");
        return;
    }

    // Check if the user entered a new edge type
    const newEdgeTypeInput = document.getElementById("new-edge-type-input");
    if (newEdgeTypeInput.style.display === "block") {
        edgeType = newEdgeTypeInput.value.trim();
        if (!edgeType) {
            alert("Please enter an edge type.");
            return;
        }
    }

    let data = window.currentEdgeData; // Get stored edge data
    data.name = edgeName;
    data.type = edgeType;

    fetch("/relations/addedge", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: data.name, type: data.type, from: data.from, to: data.to })
    })
    .then(response => response.json())
    .then(result => {
        if (result.success) {
            //data.id = result.edge_id;
            data.label = edgeName;
            edges.add(data);  // Add edge to dataset            
            closeEdgeDialog();

            console.log("New edge added:", data);

            // Notify Vis.js that the edge was successfully added
            if (typeof window.currentCallback === "function") {
                console.log("Executing callback for new edge.");
                window.currentCallback(data);
            } else {
                console.error("Callback function is missing!");
            }
        } else {
            alert("Error adding edge.");
        }
    })
    .catch(error => console.error("Error:", error));
}

function closeNodeDialog() {
    let dialog = document.getElementById("floating-node-dialog");
    if (dialog) {
        dialog.style.display = "none";  // Hide the dialog
    } else {
        console.error("Floating node dialog not found!");
    }
}

function notImplemented() {
    // return alert("This feature is not implemented yet.");
    return alert("This feature is not implemented yet. Please check back later.");
}

function createCustomGraph(pCustomGraphName) {  
    gCustomGraphName=pCustomGraphName;      
    pShape="triangle";
    pColor="#FF0000"; // Default color for custom graph
    pSize="20"; // Default size for custom graph

    // check if pCustomGraphName is null
    if (gCustomGraphName === null || gCustomGraphName === undefined || gCustomGraphName.trim() === "") {
        return alert("Enter Custom graph name");
    }

    // Make a POST request to the /create-custom-graph endpoint
    fetch("/nodes/create-custom-graph", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ name: gCustomGraphName }) // Pass the graph name as a parameter
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert(`Custom graph created successfully with ID: ${data.graph_id}`);
            // Update the floating-node-dialog with the custom graph name
            const dialogHeader = document.getElementById("dialog-header");
            if (dialogHeader) {
                dialogHeader.innerHTML = `Select Node Type for Custom Graph: ${gCustomGraphName}`;
            }            
        } else {
            alert(`Failed to create custom graph: ${data.error}`);
        }
    })
    .catch(error => {
        console.error("Error creating custom graph:", error);
        alert("An error occurred while creating the custom graph.");
    });    
    
    dialog=document.getElementById("floating-node-dialog"); 
    makeDialogDraggable(dialog); // Make the dialog draggable
    document.getElementById("CustomGraphName").value = ""; // Set the custom graph name in the input field"

    submitNodeType("CustomGraph", gCustomGraphName,pShape, pColor, pSize);    

    CloseCreateCustomGraph();
    createNode('diamond');
}


function OpenCreateCustomGraph() {
    //20250606
    // Retrieve the current graph data from the network object

    // Store the data and callback globally
    gCustomGraphName="";
    isManualGraph = true; // Set the flag to indicate manual graph creation    
    //20250723 window.currentNodeData = {};                // Prepare a fresh node object
    
    // clear data 2050828
    nodes.clear();
    edges.clear();    
    window.currentCallback = function (data) {
        console.log("Callback executed with data:", data);
    };

    // Open the dialog
    const dialog = document.getElementById("CreateCustomGraph");
    dialog.style.display = "block";
    makeDialogDraggable(dialog);

    console.log("Create Graph dialog opened with graph data:", window.currentNodeData);    
}

function CloseCreateCustomGraph() {
    const dialog = document.getElementById("CreateCustomGraph");
    dialog.style.display = "none";
}




// Close the Create Graph Dialog
function closeCreateGraphDialog() {
    isManualGraph = false; // Set the flag to indicate manual graph creation
    const dialog = document.getElementById("CreateCustomGraph");
    dialog.style.display = "none";
}

function openEdgeDialog() {
    const dialog = document.getElementById("floating-edge-dialog");
    if (dialog) {
        const data = window.currentEdgeData; // Retrieve the edge data (contains `from` and `to`)

        // Explicitly check for undefined or null
        if (data.from === undefined || data.from === null || data.to === undefined || data.to === null) {
            console.error("Source or target node is missing!");
            return;
        }

        console.log("Opening edge dialog with data:", data); // Debugging log
        const source = data.from; // Use the `from` node as the source
        const target = data.to;   // Use the `to` node as the target

        fetchEdgeTypes(source, target); // Pass source and target to fetchEdgeTypes
        dialog.style.display = "block"; // Show the dialog
    } else {
        console.error("Floating edge dialog not found!");
    }
}

// Close Choose Edges dialog
function closeChooseEdgesDialog() {
    var dialog = document.getElementById("choose-edges-dialog");
    dialog.style.display = "none";
}

// Save edge choices
function saveEdgeChoices() {
    var select = document.getElementById("choose-edges-selector");
    var selectedOptions = Array.from(select.selectedOptions).map(option => option.value);
    localStorage.setItem(`node_${selectedNodeId}_edges`, JSON.stringify(selectedOptions));
    closeChooseEdgesDialog();
}    

function openNodeDialog() {
    console.log('openNodeDialog ' + createNodeCurrentShape);

    let dialog = document.getElementById("floating-node-dialog");
    if (dialog) {
        // node-shape input no longer exists in the template; avoid referencing it.
        dialog.style.display = "block"; // Show the dialog

        fetchNodeTypes(); // Fetch and populate node types (this sets onchange and triggers initial handler)
    } else {
        console.error("Floating node dialog not found!");
    }
}

function closeEdgeDialog() {
    let dialog = document.getElementById("floating-edge-dialog");
    if (dialog) {
        dialog.style.display = "none";  // Hide the dialog
    } else {
        console.error("Floating edge dialog not found!");
    }
}

function createNode(shape) {
    //20250606
    console.log('createNode 10' + createNodeCurrentShape);
    isManualGraph = true; // Set the flag to indicate manual graph creation    
    window.currentNodeData = {};                // Prepare a fresh node object

    window.currentCallback = function (data) {
        console.log("Callback executed with data:", data);
    };    

    if (!window.currentNodeData || !window.currentCallback) {
        console.error("Data or callback is not defined. Ensure they are initialized before calling createNode.");
        return;
    }

    // Set the shape in the data object
    window.currentNodeData.shape = shape;
    createNodeCurrentShape = shape; // Update the global variable
    console.log('createNode 20 ' + createNodeCurrentShape);

    // Call the callback with the updated data
    window.currentCallback(window.currentNodeData);

    // Close the Create Graph dialog
    const dialog = document.getElementById("CreateCustomGraph");
    //20250607 dialog.style.display = "none";

    // Open the Node dialog
    openNodeDialog();

    console.log(`Node created with shape, createNode: ${shape}`);
    console.log(`Node created with shape, createNodeCurrentShape: ${createNodeCurrentShape}`);

/* 20250606
    if (shapeLabel) {
        shapeLabel.style.display = isManualGraph ? "block" : "none"; // Show if isManualGraph is true, hide otherwise
    }        
*/
    // Optionally display the selected shape in a separate element
    const shapeDisplay = document.getElementById("node-shape-display");
    if (shapeDisplay) {
        shapeDisplay.textContent = `Selected Shape: ${window.currentNodeShape || "None"}`;            
    }

    fetchNodeTypes(); // Fetch and populate node types
    
}

document.addEventListener("DOMContentLoaded", function () {

    var menu = document.getElementById("menu");
    var handle = document.getElementById("drag-handle");
    var networkContainer = document.getElementById("network-container");

    var dialog = document.getElementById("cypher-dialog");
    var isDragging = false;
    var offsetX, offsetY;    

    let isResizing = false;

    handle.addEventListener("mousedown", function (event) {
        isResizing = true;
        document.addEventListener("mousemove", resizeMenu);
        document.addEventListener("mouseup", stopResizing);
    });

    function resizeMenu(event) {
        if (!isResizing) return;
        
        let newWidth = event.clientX;
        if (newWidth < 100) newWidth = 100; // Min width
        if (newWidth > 500) newWidth = 500; // Max width

        menu.style.width = newWidth + "px";
        handle.style.left = newWidth + "px";
        networkContainer.style.left = (newWidth + 10) + "px";
        networkContainer.style.width = `calc(100% - ${newWidth + 10}px)`;
    }

    function stopResizing() {
        isResizing = false;
        document.removeEventListener("mousemove", resizeMenu);
        document.removeEventListener("mouseup", stopResizing);
    }

    // Open Cypher Query Dialog
    window.openCypherDialog = function () {
        dialog.style.display = "block";
    };

           
    window.createNodeEdgeTypes = function () {
        dialog.style.display = "block";
    };    

    // Close Cypher Query Dialog
    window.closeCypherDialog = function () {
        dialog.style.display = "none";
    };

    // Make the dialog draggable
    var header = dialog.querySelector(".dialog-header");
    header.addEventListener("mousedown", function (event) {
        isDragging = true;
        offsetX = event.clientX - dialog.offsetLeft;
        offsetY = event.clientY - dialog.offsetTop;

        document.addEventListener("mousemove", moveDialog);
        document.addEventListener("mouseup", stopDragging);
    });

    function moveDialog(event) {
        if (isDragging) {
            dialog.style.left = (event.clientX - offsetX) + "px";
            dialog.style.top = (event.clientY - offsetY) + "px";
        }
    }

    function stopDragging() {
        isDragging = false;
        document.removeEventListener("mousemove", moveDialog);
        document.removeEventListener("mouseup", stopDragging);
    }

    // Initialize the network
    // Ensure container exists
    var container = document.getElementById('network-container');
    if (!container) {
        console.error("Network container not found!");
    }

    // Initialize network
    // network = new vis.Network(container, { nodes: nodes, edges: edges }, options);
    if (!network) {
        // Initialize network only once
        network = new vis.Network(container, { nodes: nodes, edges: edges }, options);
        
        // Double-click event to open Choose Edges dialog
        // network.on("doubleClick", function (params) {
        //     console.log("Network doubleClicked"); 
        //     var nodeId = this.getNodeAt(params.pointer.DOM);
        //     console.log("Double-clicked nodeId:", nodeId);
        //     if (nodeId) {
        //         selectedNodeId = nodeId;
        //         openChooseEdgesDialog();
        //     }     
        // });
        

        console.log("Network initialized 20");
    } else {
        // Update existing network with new data
        network.setData(data);
        console.log("Network data updated");
    }    

    network.setData({ nodes: nodes, edges: edges });
    network.redraw();

    console.log("Network initialized 30");

    // Add an event listener for node clicks
    network.on("click", function (params) {
        if (showProperties && params.nodes.length > 0) {
            // A node was clicked, and the dialog is enabled
            const selectedNodes = network.getSelectedNodes();
            const nodeId = selectedNodes[0];
            const node = nodes.get(nodeId);

            if (!node) {
                console.error("Node not found.");
                return;
            }

            const dialog = document.getElementById("node-properties-dialog");
            const content = document.getElementById("node-properties-content");

            // Retrieve labels from the node object
            const labels = node.labels || ["Unknown"]; // Use stored labels or fallback to "Unknown"

            // Format the properties and include labels
            const formattedProperties = `
                <div><b>Labels:</b> ${labels.join(", ")}</div>
                ${formatProperties(node.properties)}
            `;

            // Check if the dialog is already visible
            if (dialog.style.display === "block") {
                // Refresh the dialog content
                content.innerHTML = formattedProperties;
                console.log("Dialog refreshed with new node properties and labels:", { labels, properties: node.properties });
            } else {
                // Populate the dialog with node properties and labels
                content.innerHTML = formattedProperties;

                // Show the dialog
                dialog.style.display = "block";

                // Make the dialog draggable
                makeDialogDraggable(dialog);
                console.log("Dialog opened with node properties and labels:", { labels, properties: node.properties });
            }
        }
    });

    // Function to run Cypher query and fetch results
    window.runCypherQuery = function () {
        const textarea = document.getElementById("cypher-input");
        if (!textarea) {
            console.error("Cypher input textarea not found");
            return;
        }
        const cypherQuery = textarea.value.trim();
        const clearGraph = document.getElementById("clear-graph-checkbox") && document.getElementById("clear-graph-checkbox").checked;

        // If checkbox requests clearing, do it immediately (same behavior as before)
        if (clearGraph) {
            nodes.clear();
            edges.clear();
            console.log("Graph cleared");
        }

        // If the text does NOT contain the word MATCH (case-insensitive), call OpenAI endpoint
        const hasMatch = /\bMATCH\b/i.test(cypherQuery);
        if (!hasMatch) {
            console.log("No MATCH found in textarea � calling /openai-cypher to generate/transform Cypher");
            fetch("/openai-cypher", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    natural_language: cypherQuery,
                    task: "generate",
                    execute: false
                })
            })
            .then(resp => resp.json())
            .then(data => {
                console.log("/openai-cypher response:", data);
                if (data.success) {
                    // Prefer suggested_cypher if present, otherwise the assistant response text
                    const suggested = data.suggested_cypher || data.response || "";
                    if (suggested && suggested.trim()) {
                        // Put the suggested cypher into the textarea for user review / execution
                        textarea.value = suggested.trim();
                        // Optionally auto-resize dialog height if present
                        if (typeof resizeDialog === "function") resizeDialog();
                        alert("Suggested Cypher placed into textarea. Review and press Run to execute.");
                    } else {
                        alert("No suggested Cypher was returned. See console for full response.");
                    }
                } else {
                    const err = data.error || "Unknown error from openai-cypher";
                    console.error("/openai-cypher error:", data);
                    alert("OpenAI request failed: " + err);
                }
            })
            .catch(err => {
                console.error("Error calling /openai-cypher:", err);
                alert("Error calling OpenAI service. See console for details.");
            });
            return;
        }

        // Otherwise (contains MATCH) call the original run-cypher endpoint
        fetch("/run-cypher", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query: cypherQuery })
        })
        .then(response => response.json())
        .then(data => {
            fetchNodeTypesAndVisualizeGraph(data); // Add new data to the graph
        })
        .catch(error => console.error("Error:", error));
    };

    function fetchNodeTypesAndVisualizeGraph(data) {
        console.log("data: ", data)
        fetch("/get_node_types")
            .then(response => response.json())
            .then(nodeTypes => {
                gAllowedNodeLabels = nodeTypes.map(type => type.name); // Extract node type names
    
                visualizeGraph(data, gAllowedNodeLabels);
            })
            .catch(error => console.error("Error fetching node types:", error));
    }    

    function visualizeGraph(data, allowedNodeLabels = []) {
        console.log("Visualizing graph with data:", data);
    
        // Add new nodes to the dataset
        data.nodes.forEach(node => {
            if (!nodes.get(node.id)) {
                console.log("Node object:", node);
                console.log("Node properties:", node.properties);
    
                const nodeType = node.nodeType || "Default"; // Assuming 'nodeType' is a property of the node
    
                // Fetch the shape and color for the nodeType
                fetchNodeVisuals(nodeType, (visuals) => {
                    if (!visuals) visuals = {};
    
                    // Decide shape and image safely: if shape requires an image but none provided, fall back
                    let shapeToUse = visuals.shape || createNodeCurrentShape || "ellipse";
                    let imageToUse = node.properties && node.properties.image ? node.properties.image : (visuals.image || undefined);
                    console.log('imageToUse 1: ', imageToUse);
    
                    // If an image-shape was requested but no usable image exists, fall back to ellipse
                    const isImageShapeRequested = (shapeToUse === "image" || shapeToUse === "circularImage");
                    if (isImageShapeRequested && !imageToUse) {
                        console.warn(`Node type "${nodeType}" requested image shape but no image provided; falling back to "ellipse".`);
                        shapeToUse = "ellipse";
                        imageToUse = undefined;
                    }
    
                    // Ensure a sensible default size so images are visible
                    const finalSize = (visuals.size && Number(visuals.size) > 0) ? Number(visuals.size) : 40;
    
                    // Final node object builder
                    const buildNodeObj = (finalShape, finalImage) => {
                        const n = {
                            id: node.id,
                            label: node.label,
                            shape: finalShape,
                            color: visuals.color || "#97C2FC",
                            image: finalImage,
                            size: finalSize,
                            properties: node.properties,
                            labels: node.labels || ["Unknown"]
                        };
                        return n;
                    };
    
                    // If an image is actually to be used, verify it loads before adding the node.
                    if ((shapeToUse === "image" || shapeToUse === "circularImage") && imageToUse) {
                        const img = new Image();
                        img.onload = function () {
                            const nobj = buildNodeObj(shapeToUse, imageToUse);
                            nodes.add(nobj);
                            console.log(`Node with ID ${node.id} added with shape ${shapeToUse} and color ${visuals.color}`);
                            if (network) {
                                network.redraw();
                                network.stabilize();
                            }
                        };
                        img.onerror = function () {
                            console.warn(`Image failed to load for node ${node.id}: ${imageToUse}. Falling back to ellipse.`);
                            const nobj = buildNodeObj("ellipse", undefined);
                            nodes.add(nobj);
                            if (network) {
                                network.redraw();
                                network.stabilize();
                            }
                        };
                        // start loading (relative or absolute URL)
                        img.src = imageToUse;
                    } else {
                        // Non-image nodes: add immediately
                        const nobj = buildNodeObj(shapeToUse, imageToUse);
                        nodes.add(nobj);
                        console.log(`Node with ID ${node.id} added with shape ${shapeToUse} and color ${visuals.color}`);
                        if (network) {
                            network.redraw();
                            network.stabilize();
                        }
                    }
                });
            } else {
                console.log(`Node with ID ${node.id} already exists`);
            }
        });
    
        // Add new edges to the dataset
        data.edges.forEach(edge => {
            edges.add({
                id: edge.id, // Use the Neo4j edge ID (integer)
                from: edge.from,
                to: edge.to,
                label: edge.label,
                arrows: "to"
            });
        });
    
        // Refresh and stabilize the graph
        if (network) {
            // network.redraw/stabilize are now called after each node is actually added;
            // keep these for a final pass to ensure layout is up-to-date.
            network.redraw();
            network.stabilize();
            console.log("Graph updated");
        } else {
            console.error("Network object is not initialized");
        }
    }

    var selectedNodeId = null;

    // Show context menu on right-click
    network.on("oncontext", function (params) {
        console.log("oncontext");
        params.event.preventDefault();
        const nodeId = network.getNodeAt(params.pointer.DOM);
        if (nodeId) {
            selectedNodeId = nodeId;

            // Show the context menu
            const menu = document.getElementById("node-context-menu");
            if (menu) {
                console.log("Showing custom context menu");
                menu.style.left = params.event.pageX + "px";
                menu.style.top = params.event.pageY + "px";
                menu.style.display = "block";
            }
        }
    });

    // Hide context menu on click elsewhere
    document.addEventListener("click", function () {
        const menu = document.getElementById("node-context-menu");
        menu.style.display = "none";
    });

    // Expand Node
    window.openHtml = function () {
        const selectedNodes = network.getSelectedNodes(); // Get the selected nodes
        if (selectedNodes.length === 0) {
            alert("Please select a node to expand.");
            return;
        }

        const nodeId = selectedNodes[0]; // Get the first selected node ID
        console.log("Expanding node with ID:", nodeId);

        // Open CKEditor for the node (or perform your expand logic here)
        window.open(`/edit/${nodeId}`, '_blank');
    };

    //ai
    // ---- AI Snippet Dialog (actual implementations) ----
    function openAiSnippetDialog() {
        const dlg = document.getElementById('ai-snippet-dialog');
        if (!dlg) { alert('AI dialog element missing in index.html'); return; }
        dlg.style.display = 'block';
        makeDialogDraggable(dlg);
        const out = document.getElementById('ai-snippet-output');
        if (out) out.value = '';
        const promptEl = document.getElementById('ai-prompt');
        if (promptEl) promptEl.focus();
    }
    
    function closeAiSnippetDialog() {
        const dlg = document.getElementById('ai-snippet-dialog');
        if (dlg) dlg.style.display = 'none';
    }
    
    async function askAiForSnippet() {
        const prompt = (document.getElementById('ai-prompt')?.value || '').trim();
        const output = document.getElementById('ai-snippet-output');
        if (!prompt) return alert('Please enter a prompt.');
        if (output) output.value = 'Generating…';
        try {
        const res = await fetch('/openai-generate', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ prompt })
        });
        const data = await res.json();
        if (data.success) {
            // Your Flask returns { success, response, code } – prefer code block if present.
            const snippet = (data.code && data.code.trim()) || (data.response || '').trim();
            output.value = snippet;
        } else {
            output.value = '';
            alert(data.error || 'AI generation failed.');
        }
        } catch (e) {
        console.error(e);
        if (output) output.value = '';
        alert('Error calling /openai-generate.');
        }
    }
    
    function insertAiSnippetIntoEditor() {
        const ta = document.getElementById('ai-snippet-output');
        const snippet = ta ? ta.value : '';
        if (!snippet) return;
        const doc = cmEditor.getDoc();
        const sel = doc.listSelections()[0];
        const pos = sel && sel.anchor ? sel.anchor : doc.getCursor();
        doc.replaceRange(snippet, pos);
        closeAiSnippetDialog();
    }
    
    function copyAiSnippet() {
        const ta = document.getElementById('ai-snippet-output');
        if (!ta) return;
        ta.select(); ta.setSelectionRange(0, 99999);
        document.execCommand('copy');
    }
    
    // Export these so your HTML onclicks work
    window.openAiSnippetDialog = openAiSnippetDialog;
    window.closeAiSnippetDialog = closeAiSnippetDialog;
    window.askAiForSnippet = askAiForSnippet;
    window.insertAiSnippetIntoEditor = insertAiSnippetIntoEditor;
    window.copyAiSnippet = copyAiSnippet;
  
    //end ai

    // Expand Node
    window.openHtml_v4 = function () {
        const selectedNodes = network.getSelectedNodes(); // Get the selected nodes
        if (selectedNodes.length === 0) {
            alert("Please select a node to expand.");
            return;
        }

        const nodeId = selectedNodes[0]; // Get the first selected node ID
        console.log("Expanding node with ID:", nodeId);

        // Open CKEditor for the node (or perform your expand logic here)
        window.open(`/edit_v4/${nodeId}`, '_blank');
    };    

    window.openHtml_browser = function () {
        const selectedNodes = network.getSelectedNodes(); // Get the selected nodes
        if (selectedNodes.length === 0) {
            alert("Please select a node to open in the browser.");
            return;
        }

        const nodeId = selectedNodes[0]; // Get the first selected node ID
        console.log("Opening node with ID in browser:", nodeId);

        // Open the file in the browser
        window.open(`/show-html/${nodeId}`, '_blank');
    };

    // Create html ai code
    // ==== HTML JS Editor + AI integration ====
    let htmlEditorNodeId = null;

    
    // ==== CM6-only editor handles ====
    let cmEditor = null;   // adapter exposing getValue/setValue/etc.
    let cm6View  = null;   // raw CM6 view

    async function waitForCM6(timeout = 10000) {
        const start = Date.now();
        while (typeof window.createCM6HtmlEditor !== "function") {
            if (Date.now() - start > timeout) {
                console.error("waitForCM6 timed out; createCM6HtmlEditor:", typeof window.createCM6HtmlEditor);
                return false;
            }
            await new Promise(r => setTimeout(r, 100));
        }
        console.log("waitForCM6: createCM6HtmlEditor available");
        return true;
    }

    async function ensureCodeMirror() {
        if (cmEditor) return cmEditor;

        const ok = await waitForCM6(10000);
        if (!ok || typeof window.createCM6HtmlEditor !== "function") {
            // Helpful error instead of uncaught exception
            console.error("CM6 not loaded: window.createCM6HtmlEditor is missing.");
            alert("CodeMirror (CM6) failed to load. Check console for module import errors (esm.sh).");
            throw new Error("CM6 not loaded: window.createCM6HtmlEditor is missing.");
        }

        const parent = document.getElementById('html-editor-container');
        const ta = document.getElementById('html-editor-textarea');
        if (ta) ta.style.display = 'none';           // retire the old textarea UI
        if (parent) {
            // In case CSS height is missing, enforce here too:
            // parent.style.height = '420px';
            // parent.style.maxHeight = '60vh';
            const twoThirds = Math.round(window.innerHeight * 2 / 3);
            parent.style.height = Math.max(240, twoThirds) + 'px';
            parent.style.maxHeight = 'calc(100vh - 80px)';            
            parent.style.overflow = 'hidden';
        }

        const {view, adapter} = window.createCM6HtmlEditor(parent, "", {dark: true});
        cm6View  = view;
        cmEditor = adapter;
        return cmEditor;
    }

    async function openHtml_jsEditor() {
        try {
            await ensureCodeMirror();
        } catch (err) {
            console.error("Failed to initialize editor:", err);
            alert("Editor failed to load. Check console for errors from the module script (esm.sh imports).");
            return;
        }

        const selected = network.getSelectedNodes();
        if (!selected || selected.length === 0) {
            alert("Please select a node first.");
            return;
        }
        htmlEditorNodeId = selected[0];

        // open dialog
        const dlg = document.getElementById('html-editor-dialog');
        document.getElementById('html-editor-title').textContent = `HTML Editor — node ${htmlEditorNodeId}`;
        dlg.style.display = 'block';
        makeDialogDraggable(dlg);

        

        await ensureCodeMirror();
        setEditorStatus('Loading…');

        try {
            const res = await fetch(`/get-html/${htmlEditorNodeId}`);
            const data = await res.json();
            if (data.success) {
                cmEditor.setValue(data.content || "<!-- New document -->\n");
                setEditorStatus('Loaded');
            } else {
                cmEditor.setValue("<!-- New document -->\n");
                setEditorStatus('New document (no existing HTML)');
            }
        } catch (e) {
            console.error(e);
            cmEditor.setValue("<!-- New document -->\n");
            setEditorStatus('New document (load failed)');
        }
    }
    // expose to global so inline onclick handlers (in index.html) can call it
    window.openHtml_jsEditor = openHtml_jsEditor;

    function closeHtmlEditorDialog() {
        const dlg = document.getElementById('html-editor-dialog');
        dlg.style.display = 'none';
        document.getElementById('html-editor-preview').style.display = 'none';
    }

    function setEditorStatus(msg) {
        const el = document.getElementById('html-editor-status');
        if (el) el.textContent = msg || '';
    }

    async function saveHtmlFromEditor() {
        if (!htmlEditorNodeId) return alert("No node selected.");
        const content = cmEditor ? cmEditor.getValue() : '';
        setEditorStatus('Saving…');
        try {
            const form = new FormData();
            form.append('content', content);
            const res = await fetch(`/save-html/${htmlEditorNodeId}`, { method: 'POST', body: form });
            const data = await res.json();
            if (data.success) {
                setEditorStatus('Saved ✓');
                alert(data.message || 'Saved.');
            } else {
                setEditorStatus('Save failed');
                alert(data.error || 'Failed to save.');
            }
        } catch (e) {
            console.error(e);
            setEditorStatus('Save failed');
            alert('Error while saving.');
        }
    }

    function previewEditorHtml() {
        const wrap = document.getElementById('html-editor-preview');
        const iframe = document.getElementById('html-preview-iframe');
        const html = cmEditor ? cmEditor.getValue() : '';
        wrap.style.display = 'block';
        const doc = iframe.contentDocument || iframe.contentWindow.document;
        doc.open();
        doc.write(html);
        doc.close();
    }

    // Export globals safely AFTER the functions are defined
    // Overwrite placeholders with actual implementations now that functions exist
    window.openHtml_jsEditor = openHtml_jsEditor;
    window.previewEditorHtml = previewEditorHtml;
    window.closeHtmlEditorDialog = closeHtmlEditorDialog;
    window.saveHtmlFromEditor = saveHtmlFromEditor;
    window.setEditorStatus = setEditorStatus;

    // AI snippet helpers — only overwrite if real functions were defined
    if (typeof openAiSnippetDialog !== 'undefined') window.openAiSnippetDialog = openAiSnippetDialog;
    if (typeof closeAiSnippetDialog !== 'undefined') window.closeAiSnippetDialog = closeAiSnippetDialog;
    if (typeof askAiForSnippet !== 'undefined') window.askAiForSnippet = askAiForSnippet;
    if (typeof insertAiSnippetIntoEditor !== 'undefined') window.insertAiSnippetIntoEditor = insertAiSnippetIntoEditor;
    if (typeof copyAiSnippet !== 'undefined') window.copyAiSnippet = copyAiSnippet;

    // mark implementations ready so placeholder callers can detect real implementations
    window._ai_snippet_ready = true;

    // End of html ai code

    // Collapse Node
    window.collapseNode = function () {
        if (!selectedNodeId) return;

        // Remove edges connected to the selected node
        const connectedEdges = network.getConnectedEdges(selectedNodeId);
        connectedEdges.forEach(edgeId => edges.remove(edgeId));

        // Remove nodes connected to the selected node
        const connectedNodes = network.getConnectedNodes(selectedNodeId);
        connectedNodes.forEach(nodeId => {
            if (nodeId !== selectedNodeId) nodes.remove(nodeId);
        });

        // Check for detached nodes and remove them
        const allNodes = nodes.get(); // Get all nodes in the network
        allNodes.forEach(node => {
            const connectedEdges = network.getConnectedEdges(node.id);
            if (connectedEdges.length === 0 && node.id !== selectedNodeId) {
                // Node is detached and is not the selected node, remove it from the network
                nodes.remove(node.id);
                console.log(`Detached node with ID ${node.id} removed`);
            }
        });

        console.log("Collapse operation completed");
    };

    
    window.clearNode = function () {
        if (!selectedNodeId) return;

        // Remove selected node and its connected edges
        const connectedEdges = network.getConnectedEdges(selectedNodeId);
        nodes.remove(selectedNodeId);
        alert("Node and selected edge cleared");
    };



    // Add a double-click event listener to nodes
    network.on('doubleClick', function (params) {
        // Check if a node was double-clicked
        if (params.nodes.length === 0) {
            console.log("Double-clicked on canvas, no action taken.");
            return; // Exit if no node was clicked
        }

        const nodeId = params.nodes[0]; // Get the ID of the double-clicked node
        // get id_rc of the double-clicked node
        console.log("nodeId:", nodeId);
        const nodeIdRC = nodeId;
    
        
        console.log("Expanding node with id_rc:", nodeIdRC);

        // Fetch edges for the selected node
        fetch(`/expand-node`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ node_id: nodeId })
        })
            .then(response => response.json())
            .then(data => {
                if (!data.success) {
                    console.error("Error expanding node:", data.error);
                    return;
                }

                console.log("Data received from /expand-node:", data);

                // Add nodes to the graph            
                data.nodes.forEach(node => {
                    if (!nodes.get(node.id)) {
                        nodes.add({
                            id: node.id,
                            //label: node.label,
                            label: node.label,
                            labels: node.labels || ["not defined"], // Store labels in the node object
                            properties: node.properties, 
                            shape: node.shape || "ellipse",                            
                            color: node.properties && node.properties.color ? node.properties.color : "#97C2FC",
                        });
                        console.log(`Node with ID ${node.id} added`);
                    } else {
                        console.log(`Node with ID ${node.id} already exists`);
                    }
                });




                // Add edges to the graph
                data.edges.forEach(edge => {
                    if (!edges.get(edge.id)) {
                        edges.add({
                            id: edge.id,
                            from: edge.from,
                            to: edge.to,
                            label: edge.label,
                            arrows: "to"
                        });
                        console.log(`Edge with ID ${edge.id} added`);
                    } else {
                        console.log(`Edge with ID ${edge.id} already exists`);
                    }
                });

                // Refresh the graph
                if (network) {
                    network.redraw();
                    network.stabilize();
                    console.log("Graph updated");
                } else {
                    console.error("Network object is not initialized");
                }
            })
            .catch(error => console.error("Error expanding node:", error));
    });
});



// Expand/collapse menu items
document.querySelectorAll('.menu-container ul li').forEach(function(item) {
    item.addEventListener('click', function(event) {
        const submenu = this.querySelector('ul');
        if (submenu) {
            submenu.style.display = submenu.style.display === 'block' ? 'none' : 'block';
        }
        event.stopPropagation();
    });
});

var container = document.getElementById("network-container");
container.addEventListener("contextmenu", function (event) {
    console.log("Contextmenu event triggered on network-container");
    event.preventDefault(); // Disable the browser's default context menu
//});

//document.addEventListener("DOMContentLoaded", function () {
    var selectedNodeId = null;

    var container = document.getElementById("network-container");
    if (!container) {
        console.error("Network container not found!");
        return;
    }

    // Disable the browser's default context menu
    container.addEventListener("contextmenu", function (event) {
        console.log("Contextmenu event triggered on network-container");
        event.preventDefault();
    });

    // Initialize the network
    if (!network) {
        network = new vis.Network(container, { nodes: nodes, edges: edges }, options);
        console.log("Network initialized:", network);

        // Attach the oncontext event listener
        network.on("oncontext", function (params) {
            console.log("oncontext event triggered");
            params.event.preventDefault(); // Prevent the default right-click behavior

            const nodeId = network.getNodeAt(params.pointer.DOM);
            console.log("Right-clicked node ID:", nodeId);

            if (nodeId) {
                selectedNodeId = nodeId;

                // Show the custom context menu
                const menu = document.getElementById("node-context-menu");
                if (menu) {
                    console.log("Showing custom context menu");
                    menu.style.left = params.event.pageX + "px";
                    menu.style.top = params.event.pageY + "px";
                    menu.style.display = "block";
                } else {
                    console.error("Custom context menu not found");
                }
            }
        });
    } else {
        console.error("Network object already initialized");
    }

    // Hide the context menu on click elsewhere
    document.addEventListener("click", function () {
        const menu = document.getElementById("node-context-menu");
        if (menu) {
            menu.style.display = "none";
        }
    });

    if (!network) {
        console.error("Network object is not initialized.");
    } else {
        console.log("Network object is initialized:", network);
    }
});

function fetchNodeTypes() {
    fetch("/get_node_types")
        .then(response => response.json())
        .then(nodeTypes => {
            console.log("Node types received:", nodeTypes); // Debugging log
            let selector = document.getElementById("node-type-selector");
            if (selector) {
                selector.innerHTML = ""; // Clear existing options
                nodeTypes.forEach(type => {
                    let option = document.createElement("option");
                    option.value = type.name;
                    option.textContent = type.name;
                    selector.appendChild(option);
                });

                // Attach onchange handler (replace any previous handler)
                selector.onchange = function () {
                    handleNodeTypeSelection(this.value);
                };

                // trigger handler for initial selection if any
                if (selector.options.length > 0) {
                    handleNodeTypeSelection(selector.value);
                }
            } else {
                console.error("Node type selector not found!");
            }
        })
        .catch(error => console.error("Error fetching node types:", error));
}

// New: show/hide image input and preview
function toggleNodeImageField(show, presetUrl) {
    const field = document.getElementById("node-image-field");
    const urlInput = document.getElementById("node-image-url");
    const preview = document.getElementById("node-image-preview");
    const previewImg = document.getElementById("node-image-preview-img");

    if (!field || !urlInput || !preview || !previewImg) return;

    if (show) {
        field.style.display = "block";
        if (presetUrl) {
            urlInput.value = presetUrl;
            previewImg.src = presetUrl;
            preview.style.display = presetUrl ? "block" : "none";
        } else {
            preview.style.display = "none";
            previewImg.src = "";
        }

        // update preview when user edits
        urlInput.oninput = function () {
            const val = this.value.trim();
            if (val) {
                previewImg.src = val;
                preview.style.display = "block";
            } else {
                previewImg.src = "";
                preview.style.display = "none";
            }
        };
    } else {
        field.style.display = "none";
        urlInput.oninput = null;
        urlInput.value = "";
        preview.style.display = "none";
        previewImg.src = "";
    }
}

// New: when node type changes, fetch visuals and show image field if needed
function handleNodeTypeSelection(nodeType) {
    if (!nodeType) {
        toggleNodeImageField(false);
        return;
    }

    // Reuse existing fetchNodeVisuals helper; it now returns the whole visuals object
    fetchNodeVisuals(nodeType, (visuals) => {
        if (!visuals) {
            toggleNodeImageField(false);
            return;
        }
        const isImageShape = (visuals.shape === "image" || visuals.shape === "circularImage");
        toggleNodeImageField(isImageShape, visuals.image || "");
    });
}

function fetchEdgeTypes(source, target) {
    if (source === undefined || source === null || target === undefined || target === null) {
        console.error("Source or target node is missing!");
        return;
    }

    fetch(`/get_edge_types?source=${source}&target=${target}`)
        .then(response => response.json())
        .then(responseData => {
            console.log("Edge types response received:", responseData); // Debugging log

            // Access the `edge_types` array from the response
            const edgeTypes = responseData.edge_types;

            // Validate that edgeTypes is an array
            if (!Array.isArray(edgeTypes)) {
                console.error("Invalid response format: edge_types is not an array", responseData);
                alert("Failed to fetch edge types. Please check the server response.");
                return;
            }

            let selector = document.getElementById("edge-type-selector");
            let input = document.getElementById("new-edge-type-input");

            if (selector && input) {
                selector.innerHTML = ""; // Clear existing options

                if (edgeTypes.length > 0) {
                    // Add existing edge types to the dropdown
                    edgeTypes.forEach(type => {
                        let option = document.createElement("option");
                        option.value = type;
                        option.textContent = type;
                        selector.appendChild(option);
                    });

                    // Add "Add New..." option
                    let addNewOption = document.createElement("option");
                    addNewOption.value = "add-new";
                    addNewOption.textContent = "Add New...";
                    selector.appendChild(addNewOption);

                    // Show the dropdown and hide the input field
                    selector.style.display = "block";
                    input.style.display = "none";

                    // Add event listener to handle "Add New..." selection
                    selector.addEventListener("change", function () {
                        if (this.value === "add-new") {
                            console.log("Add New selected, showing input field."); // Debugging log
                            this.style.display = "none"; // Hide the dropdown
                            input.style.display = "block"; // Show the text input
                            input.focus(); // Focus on the text input
                        }
                    });
                } else {
                    // No edge types available, directly show the input field
                    console.log("No edge types available, showing input field directly.");
                    selector.style.display = "none"; // Hide the dropdown
                    input.style.display = "block"; // Show the text input
                    input.focus(); // Focus on the text input
                }
            } else {
                console.error("Edge type selector or input field not found!");
            }
        })
        .catch(error => {
            console.error("Error fetching edge types:", error);
            alert("An error occurred while fetching edge types.");
        });
}

function uuidv4() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
        const r = Math.random() * 16 | 0, v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}



function saveNewEdgeType(input) {
    const newType = input.value.trim();
    if (newType) {
        // Add the new type to the dropdown
        const selector = document.getElementById("edge-type-selector");
        const newOption = document.createElement("option");
        newOption.value = newType;
        newOption.textContent = newType;
        selector.appendChild(newOption);

        // Select the new option and hide the input
        selector.value = newType;
        input.style.display = "none";
        selector.style.display = "block";
    } else {
        // If no value is entered, reset to the dropdown
        input.style.display = "none";
        const selector = document.getElementById("edge-type-selector");
        selector.style.display = "block";
        selector.value = ""; // Reset selection
    }
}

function openCreateNodeTypeDialog() {
    dialog = document.getElementById("create-node-type-dialog");
    dialog.style.display = "block"; // Close the Create Graph dialog if open
    makeDialogDraggable(dialog);
    //document.getElementById("create-node-type-dialog").style.display = "block";
}

function closeCreateNodeTypeDialog() {
    document.getElementById("create-node-type-dialog").style.display = "none";
}

// Add a new property dynamically in the Create Node Type dialog
function addNewNodeTypePropertyField() {
    const content = document.getElementById("node-type-properties-content");
    const newPropertyDiv = document.createElement("div");

    newPropertyDiv.innerHTML = `
        <input type="text" placeholder="Property Key" class="new-node-type-property-key" />
        <input type="text" placeholder="Property Value" class="new-node-type-property-value" />
    `;
    content.appendChild(newPropertyDiv);
}

// Update the submitNodeType function to include properties
function submitNodeType(pNodeType, pName, pShape, pColor, pSize) {
    const name = document.getElementById("node-type-name").value || pName;
    const shape = pShape || document.getElementById("node-type-shape").value;
    const color = pColor || document.getElementById("node-type-color").value ;
    const size = parseInt(pSize || document.getElementById("node-type-size").value, 10);

    if (!name) {
        alert("Node type name is required!");
        return;
    }

    // Collect properties
    const properties = {};
    const keys = document.querySelectorAll(".new-node-type-property-key");
    const values = document.querySelectorAll(".new-node-type-property-value");

    keys.forEach((keyInput, index) => {
        const key = keyInput.value.trim();
        const value = values[index].value.trim();
        if (key) {
            properties[key] = value;
        }
    });

    fetch("/nodes/add_node_type", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({pNodeType,  name, shape, color, size, properties })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert("Node type created successfully!");
            closeCreateNodeTypeDialog();
            fetchNodeTypes(); // Optionally refresh the node types dropdown
        } else {
            alert("Error: " + data.error);
        }
    })
    .catch(error => {
        console.error("Error creating node type:", error);
        alert("Failed to create node type.");
    });
}

function formatProperties(properties) {
    if (!properties || typeof properties !== "object") {
        return "No properties available.";
    }

    // Render each property as an editable input or textarea field
    return Object.entries(properties)
        .map(([key, value]) => {
            const isLongText = typeof value === "string" && value.length > 50; // Use textarea for long text
            return `
                <div>
                    <label><b>${key}:</b></label>
                    ${
                        isLongText
                            ? `<textarea id="property-${key}" rows="4" style="width: 100%;">${value}</textarea>`
                            : `<input type="text" id="property-${key}" value="${value}" />`
                    }
                </div>
            `;
        })
        .join("");
}

function deleteSelected() {
    // Get selected nodes and edges
    const selected = network.getSelection();
    const selectedNodes = selected.nodes;
    const selectedEdges = selected.edges;

    if (selectedNodes.length === 0 && selectedEdges.length === 0) {
        alert("No nodes or edges selected for deletion.");
        return;
    }

    // Log the selected edges and their details for debugging
    console.log("Selected edges for deletion:", selectedEdges);
    selectedEdges.forEach(edgeId => {
        const edge = edges.get(edgeId);
        console.log(`Edge ID: ${edgeId}, Edge Details:`, edge);
    });

    // Confirm deletion
    if (!confirm("Are you sure you want to delete the selected nodes and edges?")) {
        return;
    }

    // Use string id_rc values instead of parsing integers
    const edgeIds = selectedEdges.map(edgeId => {
        const edge = edges.get(edgeId);
        // Use the actual Neo4j edge id_rc (string) if present, otherwise use the vis id
        return edge ? String(edge.id) : String(edgeId);
    });

    const nodeIds = selectedNodes.map(nodeId => String(nodeId));

    // Send the selected nodes and edges to the backend for deletion
    fetch("/delete-selected", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nodes: nodeIds, edges: edgeIds })
    })
    .then(response => response.json())
    .then(result => {
        if (result.success) {
            // Remove nodes and edges from the graph
            nodes.remove(selectedNodes);
            edges.remove(selectedEdges);

            alert("Selected nodes and edges deleted successfully.");
        } else {
            alert("Error deleting selected nodes and edges: " + result.error);
        }
    })
    .catch(error => {
        console.error("Error deleting selected nodes and edges:", error);
        alert("An error occurred while deleting the selected nodes and edges.");
    });
}

function saveNodeProperties() {
    const content = document.getElementById("node-properties-content");
    const inputs = content.querySelectorAll("input[id^='property-']");
    const newKeys = content.querySelectorAll(".new-property-key");
    const newValues = content.querySelectorAll(".new-property-value");

    const updatedProperties = {};

    // Collect existing properties
    inputs.forEach(input => {
        const key = input.id.replace("property-", "");
        updatedProperties[key] = input.value;
    });

    // Collect new properties
    newKeys.forEach((keyInput, index) => {
        const key = keyInput.value.trim();
        const value = newValues[index].value.trim();
        if (key) {
            updatedProperties[key] = value;
        }
    });

    const selectedNodes = network.getSelectedNodes();
    if (selectedNodes.length === 0) {
        alert("No node selected.");
        return;
    }

    const nodeId = selectedNodes[0];

    // Send the updated properties to the backend
    fetch("/nodes/update-node-properties", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ node_id: nodeId, properties: updatedProperties })
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! Status: ${response.status}`);
        }
        const contentType = response.headers.get("Content-Type");
        if (contentType && contentType.includes("application/json")) {
            return response.json();
        } else {
            throw new Error("Unexpected response format");
        }
    })
    .then(data => {
        if (data.success) {
            // Update the node in the Vis.js network
            nodes.update({
                id: nodeId,
                properties: updatedProperties // Update the properties in the dataset
            });

            alert("Node properties updated successfully.");
            closeNodePropertiesDialog();
        } else {
            alert("Error updating node properties: " + data.error);
        }
    })
    .catch(error => {
        console.error("Error updating node properties:", error);
        alert("An error occurred while updating node properties.");
    });
}

// Add a new property dynamically
function addNewPropertyField() {
    const content = document.getElementById("node-properties-content");
    const newPropertyDiv = document.createElement("div");

    newPropertyDiv.innerHTML = `
        <input type="text" placeholder="Property Key" class="new-property-key" />
        <input type="text" placeholder="Property Value" class="new-property-value" />
    `;
    content.appendChild(newPropertyDiv);
}

function isPhysicsEnabled() {
    if (network && network.physics) {
        return network.physics.options.enabled; // Check if physics is enabled
    }
    console.error("Network object is not initialized or physics is not available");
    return false;
}

function changePhysics() {
    if (network) {
        // Check if physics is currently enabled
        const physicsEnabled = network.physics.options.enabled;

        // Toggle the physics state
        network.setOptions({ physics: !physicsEnabled });

        // Update the button label
        const physicsToggle = document.getElementById("physicsToggle");
        if (physicsToggle) {
            physicsToggle.innerText = physicsEnabled ? "Enable physics" : "Disable physics";
        }

        console.log(`Physics ${!physicsEnabled ? "enabled" : "disabled"}`);
    } else {
        console.error("Network object is not initialized");
    }
}

function openNodePropertiesDialog() {
    showProperties = true; // Enable showing properties
    const selectedNodes = network.getSelectedNodes();
    if (selectedNodes.length === 0) {
        alert("Please select a node to view its properties.");
        return;
    }

    const nodeId = selectedNodes[0];
    const node = nodes.get(nodeId);

    if (!node) {
        alert("Node not found.");
        return;
    }

    const dialog = document.getElementById("node-properties-dialog");
    const content = document.getElementById("node-properties-content");

    // Retrieve labels from the node object
    const labels = node.labels || ["Unknown"]; // Use stored labels or fallback to "Unknown"

    // Format the properties and include labels
    const formattedProperties = `
        <div><b>Labels:</b> ${labels.join(", ")}</div>
        ${formatProperties(node.properties)}
    `;

    // Populate the dialog with node properties and labels
    content.innerHTML = formattedProperties;

    // Show the dialog
    dialog.style.display = "block";

    // Make the dialog draggable
    makeDialogDraggable(dialog);
    console.log("Dialog opened with node properties and labels:", { labels, properties: node.properties });
}

function closeNodePropertiesDialog() {
    showProperties = false; // Disable showing properties
    const dialog = document.getElementById("node-properties-dialog");
    dialog.style.display = "none";
}

function makeDialogDraggable(dialog) {
    const header = dialog.querySelector(".dialog-header");
    let isDragging = false;
    let offsetX, offsetY;

    header.addEventListener("mousedown", function (event) {
        isDragging = true;
        offsetX = event.clientX - dialog.offsetLeft;
        offsetY = event.clientY - dialog.offsetTop;

        document.addEventListener("mousemove", moveDialog);
        document.addEventListener("mouseup", stopDragging);
    });

    function moveDialog(event) {
        if (isDragging) {
            dialog.style.left = (event.clientX - offsetX) + "px";
            dialog.style.top = (event.clientY - offsetY) + "px";
        }
    }

    function stopDragging() {
        isDragging = false;
        document.removeEventListener("mousemove", moveDialog);
        document.removeEventListener("mouseup", stopDragging);
    }
}

function fetchNodeVisuals(nodeType, callback) {
    fetch("/nodes/get_node_type_visuals", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nodeType: nodeType })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            console.log("Node visuals received:", data);
            // Pass the whole visuals object to the callback for richer usage
            callback(data);
        } else {
            console.error("Error fetching node visuals:", data.error);
            alert("Error: " + data.error);
            callback(null);
        }
    })
    .catch(error => {
        console.error("Error fetching node visuals:", error);
        alert("An error occurred while fetching node visuals.");
        callback(null);
    });

}

function showCustomGraphName() {
    alert(gCustomGraphName || "No custom graph name set.");
}

function saveCustomGraph() {
    if (!gCustomGraphName) {
        alert("Custom graph name is not set. Please create a custom graph first.");
        return;
    }

    const graphNodes = nodes.get(); // Get all nodes from the graph
    console.log("Sending data to backend:", { customGraphName: gCustomGraphName, nodes: graphNodes });
    console.log("nodes:", { Pnodes : nodes.get() });
    

    const positions = network.getPositions(); // Get positions for all nodes


    const nodeData = graphNodes.map(node => {
        // Prefer explicit id_rc property (top-level), then properties.id_rc, then fallback to vis id
        const chosenId = node.id_rc || (node.properties && node.properties.id_rc) || node.id;
        return {
            id: chosenId,
            // include vis id as fallback/for reference if needed
            vis_id: node.id,
            x: positions[node.id]?.x || 0, // Get node position
            y: positions[node.id]?.y || 0, // Get node position
            shape: node.shape || "ellipse", // Default shape
            properties: node.properties || {} // Node properties
        };
    });

    fetch("/nodes/connect-custom-graph-position", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ customGraphName: gCustomGraphName, nodes: nodeData })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert("Custom graph saved successfully!");
        } else {
            alert("Error saving custom graph: " + data.error);
        }
    })
    .catch(error => {
        console.error("Error saving custom graph:", error);
        alert("An error occurred while saving the custom graph.");
    });

}

//Function to load graph previously saved by saveCustomGraph
function loadCustomGraph(pCustomGraphName) {
    console.log(`Loading custom graph: ${pCustomGraphName}`);

    if (!pCustomGraphName || pCustomGraphName.trim() === "") {
        alert("Please enter a valid custom graph name.");
        return;
    } else {
        gCustomGraphName = pCustomGraphName; // Set the global variable for the custom graph name
    }

    // Send a GET request to the Flask endpoint
    fetch(`/loadCustomGraph/${encodeURIComponent(pCustomGraphName)}`, {
        method: "GET",
        headers: {
            "Content-Type": "application/json"
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            console.log("Custom graph loaded successfully:", data);

            // Clear the existing graph
            nodes.clear();
            edges.clear();

            // Add nodes to the graph
            data.nodes.forEach(node => {
                nodes.add({
                    id: node.id,
                    label: node.label,
                    shape: node.shape,
                    color: node.color,
                    x: node.x,
                    y: node.y,
                    properties: node.properties,
                    image: node.image,
                    size: node.size,
                    labels: node.labels || ["not defined"], // Store labels in the node object
                    color: node.color,
                });
            });

            // Add edges to the graph
            data.edges.forEach(edge => {
                console.log("Adding edge:", edge.id);
                edges.add({
                    id: edge.id,
                    from: edge.from,
                    to: edge.to,
                    label: edge.label,
                    arrows: "to"
                });
            });

            // Refresh the graph
            refreshGraph();
            alert(`Custom graph "${pCustomGraphName}" loaded successfully.`);
        } else {
            console.error("Error loading custom graph:", data.error);
            alert(`Failed to load custom graph: ${data.error}`);
        }
    })
    .catch(error => {
        console.error("Error loading custom graph:", error);
        alert("An error occurred while loading the custom graph.");
    });
}



function refreshGraph() {
    if (network) {
        console.log("Refreshing graph with nodes:", nodes.get());
        network.setData({ nodes: nodes, edges: edges });
        network.redraw(); // Redraw the graph
        console.log("Graph refreshed with updated nodes and edges.");
    } else {
        console.error("Network object is not initialized.");
    }
}

function cancelConnection() {
    const selectedEdges = network.getSelectedEdges(); // Get the selected edges

    if (selectedEdges.length === 0) {
        alert("Please select a connection (edge) to cancel.");
        return;
    }

    const edgeId = selectedEdges[0]; // Get the first selected edge ID
    console.log("Canceling connection with edge ID:", edgeId);

    // Send a request to the backend to delete the edge (use id_rc string)
    fetch(`/delete-selected`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ edges: [String(edgeId)] })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Remove the edge from the graph
            edges.remove(edgeId);
            alert("Connection canceled successfully.");
        } else {
            alert("Error canceling connection: " + data.error);
        }
    })
    .catch(error => {
        console.error("Error canceling connection:", error);
        alert("An error occurred while canceling the connection.");
    });
}

// --- New: Add Existing Nodes flow ---
// Open the dialog to let user pick a node type and then an existing node to add
function AddExistingNodes() {
    isManualGraph = true; // we are adding nodes manually
    const dialog = document.getElementById("existing-nodes-dialog");
    if (!dialog) {
        console.error("Existing nodes dialog element not found!");
        return;
    }
    dialog.style.display = "block";
    makeDialogDraggable(dialog);

    // populate node type selector
    const selector = document.getElementById("existing-node-type-selector");
    if (!selector) return;
    selector.innerHTML = "<option value=''>Loading...</option>";

    fetch("/get_node_types")
        .then(resp => resp.json())
        .then(nodeTypes => {
            selector.innerHTML = ""; // clear
            nodeTypes.forEach(type => {
                const opt = document.createElement("option");
                opt.value = type.name;
                opt.textContent = type.name;
                selector.appendChild(opt);
            });
            // optionally select first and trigger load
            if (selector.options.length > 0) {
                selector.selectedIndex = 0;
                onExistingNodeTypeChange(selector.value);
            }
        })
        .catch(err => {
            console.error("Failed to fetch node types:", err);
            selector.innerHTML = "<option value=''>(failed to load)</option>";
        });
}

function closeExistingNodesDialog() {
    const dialog = document.getElementById("existing-nodes-dialog");
    if (dialog) dialog.style.display = "none";
}

// Called when user selects a node type in the "Add Existing Nodes" dialog
function onExistingNodeTypeChange(nodeType) {
    const list = document.getElementById("existing-nodes-list");
    if (!list) return;
    list.innerHTML = "Loading...";

    if (!nodeType) {
        list.innerHTML = "<div style='color:#777'>Please select a node type</div>";
        return;
    }

    fetch("/nodes/get_nodes_by_type", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nodeType: nodeType })
    })
    .then(resp => resp.json())
    .then(data => {
        if (!data.success) {
            list.innerHTML = `<div style="color:red">Error: ${data.error || "unknown"}</div>`;
            return;
        }
        renderExistingNodeList(data.nodes || []);
    })
    .catch(err => {
        console.error("Error fetching nodes by type:", err);
        list.innerHTML = `<div style="color:red">Failed to load nodes</div>`;
    });
}

// Render clickable list of nodes inside the dialog
function renderExistingNodeList(nodesArray) {
    const list = document.getElementById("existing-nodes-list");
    if (!list) return;
    list.innerHTML = "";

    if (!Array.isArray(nodesArray) || nodesArray.length === 0) {
        list.innerHTML = "<div style='color:#777'>No nodes found for this type</div>";
        return;
    }

    nodesArray.forEach(node => {
        const item = document.createElement("div");
        item.style.padding = "6px";
        item.style.borderBottom = "1px solid #eee";
        item.style.cursor = "pointer";
        item.title = JSON.stringify(node.properties || {});
        const nodeLabel = node.label || (node.properties && node.properties.name) || (`${(node.labels && node.labels[0]) || "Node"} (${node.id})`);
        item.textContent = `${nodeLabel} (id:${node.id})`;
        item.onclick = function () {
            addExistingNodeToGraph(node);
        };
        list.appendChild(item);
    });
}

// Add selected existing node into the vis.js graph
function addExistingNodeToGraph(node) {
    if (!node) return;
    // prefer using the Neo4j id_rc as the vis id when available, otherwise fallback to a namespaced id
    const neo4jId = node.properties && node.properties.id_rc ? String(node.properties.id_rc) : null;
    const visId = neo4jId || `n${node.id}`; // string id

    if (nodes.get(visId)) {
        alert("Node already present in the graph.");
        return;
    }

    // Fetch visuals for the node's primary label if available, then add
    const primaryLabel = (node.labels && node.labels[0]) || null;
    if (primaryLabel) {
        fetchNodeVisuals(primaryLabel, (visuals) => {
            if (!visuals) visuals = {};
            let shape = visuals.shape || createNodeCurrentShape || "ellipse";
            let image = visuals.image || undefined;
            if ((shape === "image" || shape === "circularImage") && !image) {
                console.warn(`Node type "${primaryLabel}" requested image shape but no image provided; falling back to "ellipse".`);
                shape = "ellipse";
                image = undefined;
            }

            const nobj = {
                id: visId,
                id_rc: neo4jId || undefined,
                label: node.label || (node.properties && node.properties.name) || primaryLabel,
                shape: shape,
                color: visuals.color || "#97C2FC",
                image: image,
                properties: node.properties || {},
                labels: node.labels || []
            };
            nodes.add(nobj);
            nodeIdToNameMap.set(visId, nobj.label);
            refreshGraph();
            alert("Node added to graph.");
        });
    } else {
        // fallback add if no label known
        const nobj = {
            id: visId,
            id_rc: neo4jId || undefined,
            label: node.label || (node.properties && node.properties.name) || `node_${node.id}`,
            shape: createNodeCurrentShape || "ellipse",
            color: "#97C2FC",
            properties: node.properties || {},
            labels: node.labels || []
        };
        nodes.add(nobj);
        nodeIdToNameMap.set(visId, nobj.label);
        refreshGraph();
        alert("Node added to graph.");
    }
    // Optionally close the dialog after adding
    // closeExistingNodesDialog();
}

// Add new function to remove node from custom graph
async function removeNodeCustomGraph() {
    // Get selected nodes from the network
    const selected = network.getSelectedNodes();
    if (!selected || selected.length === 0) {
        alert("Please select a node to remove from custom graph.");
        return;
    }

    const visId = selected[0];
    const node = nodes.get(visId);
    if (!node) {
        alert("Selected node not found in dataset.");
        return;
    }

    // Prefer id_rc, then properties.id_rc, then node.id (vis id or stored id)
    const idParam = node.id_rc || (node.properties && (node.properties.id_rc || node.properties.id)) || node.id;

    if (!idParam) {
        alert("Unable to determine node identifier to remove.");
        return;
    }

    if (!confirm("Remove this node from the custom graph? This will remove its custom-graph references and stored position.")) {
        return;
    }

    const nodeIdStr = String(idParam);
    const payload = { node_id: nodeIdStr };

    // Sequence of attempts to handle different server expectations (POST/DELETE/GET or different endpoint)
    const attempts = [
        { method: "POST", url: "/remove-node-custom-graph", body: true },
        { method: "POST", url: "/nodes/remove-node-custom-graph", body: true },
        // Some servers expect DELETE without JSON body, with a query param
        { method: "DELETE", url: `/remove-node-custom-graph?node_id=${encodeURIComponent(nodeIdStr)}`, body: false },
        // Last resort: GET with query param
        { method: "GET", url: `/remove-node-custom-graph?node_id=${encodeURIComponent(nodeIdStr)}`, body: false }
    ];

    let finalResult = null;
    for (const attempt of attempts) {
        try {
            console.log(`Attempting ${attempt.method} ${attempt.url}`);
            const options = {
                method: attempt.method,
                headers: {}
            };
            if (attempt.body) {
                options.headers["Content-Type"] = "application/json";
                options.body = JSON.stringify(payload);
            }

            const resp = await fetch(attempt.url, options);

            // If server returns 405 Method Not Allowed, try next attempt
            if (resp.status === 405) {
                console.warn(`${attempt.method} ${attempt.url} -> 405 Method Not Allowed, trying next option`);
                continue;
            }

            // Read response safely depending on content type
            const contentType = resp.headers.get("Content-Type") || "";
            const text = await resp.text();

            // If the response is not JSON, show status and returned HTML/text for debugging
            if (!contentType.toLowerCase().includes("application/json")) {
                console.error(`Non-JSON response from ${attempt.url}:`, { status: resp.status, body: text });
                alert(`Server returned non-JSON response (status ${resp.status}). See console for details.`);
                // If it was an error page (HTML), don't try further attempts � but continue loop if you prefer
                // We'll stop here to avoid accidental repeated side-effects.
                finalResult = { success: false, error: `Non-JSON response (status ${resp.status}).` };
                break;
            }

            // Parse JSON safely now
            let result = null;
            try {
                result = JSON.parse(text);
            } catch (parseErr) {
                console.error("Failed to parse JSON from response:", text, parseErr);
                alert("Failed to parse server response. See console for details.");
                finalResult = { success: false, error: "Invalid JSON response" };
                break;
            }

            // If backend indicated failure, bubble up
            if (!result || !result.success) {
                console.warn("Backend returned failure:", result);
                finalResult = result;
                break;
            }

            // Success
            finalResult = result;
            break;
        } catch (err) {
            console.error(`Error while trying ${attempt.method} ${attempt.url}:`, err);
            // try next attempt
        }
    }

    if (!finalResult) {
        alert("Failed to remove node from custom graph: no successful response from server. Check console for details.");
        return;
    }

    if (!finalResult.success) {
        alert("Failed to remove node from custom graph: " + (finalResult.error || "unknown error"));
        return;
    }

    // If backend returned the list of removed vis ids, use it; otherwise use heuristics
    const nodesToRemove = new Set();

    if (finalResult.removed_vis_ids && Array.isArray(finalResult.removed_vis_ids)) {
        finalResult.removed_vis_ids.forEach(id => nodesToRemove.add(id));
    } else {
        nodes.get().forEach(n => {
            if (String(n.id) === String(visId) ||
                String(n.id) === String(idParam) ||
                String(n.id_rc || "") === String(idParam) ||
                (n.properties && (String(n.properties.id_rc || "") === String(idParam) || String(n.properties.id || "") === String(idParam))) ||
                (n.labels && n.labels.includes("customGraphNode") && (String(n.id_rc || "") === String(idParam) || String(n.id) === String(idParam)))
            ) {
                nodesToRemove.add(n.id);
            }
        });
    }

    // Remove connected edges first
    nodesToRemove.forEach(nid => {
        try {
            const connectedEdgeIds = network.getConnectedEdges(nid) || [];
            if (connectedEdgeIds.length > 0) edges.remove(connectedEdgeIds);
        } catch (e) {
            // network.getConnectedEdges may throw if node not present; ignore
        }
    });

    if (nodesToRemove.size > 0) {
        nodes.remove(Array.from(nodesToRemove));
    } else {
        // Ensure at least the selected visId is removed
        try { nodes.remove(visId); } catch (e) {}
    }

    refreshGraph();
    alert("Node removed from custom graph.");
}

// --- Add safe placeholders so inline onclick handlers won't throw before DOMContentLoaded ---
window.openHtml_jsEditor = window.openHtml_jsEditor || function(){ console.warn("openHtml_jsEditor: not initialized"); };
window.previewEditorHtml = window.previewEditorHtml || function(){ console.warn("previewEditorHtml: not initialized"); };
window.closeHtmlEditorDialog = window.closeHtmlEditorDialog || function(){ console.warn("closeHtmlEditorDialog: not initialized"); };
window.saveHtmlFromEditor = window.saveHtmlFromEditor || function(){ console.warn("saveHtmlFromEditor: not initialized"); };
window.setEditorStatus = window.setEditorStatus || function(msg){ console.warn("setEditorStatus:", msg); };

// AI snippet placeholders
window.openAiSnippetDialog = window.openAiSnippetDialog || function(){ console.warn("openAiSnippetDialog: not initialized"); };
window.closeAiSnippetDialog = window.closeAiSnippetDialog || function(){ console.warn("closeAiSnippetDialog: not initialized"); };
window.askAiForSnippet = window.askAiForSnippet || function(){ console.warn("askAiForSnippet: not initialized"); };
window.insertAiSnippetIntoEditor = window.insertAiSnippetIntoEditor || function(){ console.warn("insertAiSnippetIntoEditor: not initialized"); };
window.copyAiSnippet = window.copyAiSnippet || function(){ console.warn("copyAiSnippet: not initialized"); };




