# Import necessary packages.
import omero
import numpy as np
import getpass
import omero.model
from omero.model import MapAnnotationI
from omero.rtypes import rstring, robject, rlong, rfloat
from omero.gateway import BlitzGateway
from omero.model import NamedValue
from rdflib import Graph, Namespace



# 1. Prompt user for inputs
print("Welcome! Please provide the following details.")

username = input("OMERO Username: ")
password = getpass.getpass("OMERO Password: ")
host = input("OMERO Host (e.g., localhost or your.server.com): ")
rdf_file = input("Path to your RDF file (turtle format) (e.g., /path/to/file.rdf): ")
rdf_file = rdf_file.strip('"').strip("'")

# 2. Prompt for OMERO Image ID
image_id = input("Enter the OMERO Image ID to annotate: ")

# 3. Connect to OMERO
print("\nConnecting to OMERO...")
conn = BlitzGateway(username, password, host=host)
if not conn.connect():
    print("Failed to connect to OMERO. Please check your credentials.")
    exit(1)
print("Successfully connected to OMERO.")


# 4. Parse the RDF file
graph = Graph()
try:
    graph.parse(rdf_file, format="turtle")  # Adjust format if needed
    print(f"Successfully parsed RDF file: {rdf_file}")
except Exception as e:
    print(f"Failed to parse RDF file: {e}")
    exit(1)

    

# 5. Functions to group triples and upload them to omero.

# Function to group triples by namespace and seperate key-value pairs for same key.
def group_triples_by_namespace(graph):
    namespaces = {}
    for subject, predicate, obj in graph:
        # Split predicate into namespace and local name
        ns, local_name = predicate.split("#") if "#" in predicate else predicate.rsplit("/", 1)
        # Group predicates by their namespace
        if ns not in namespaces:
            namespaces[ns] = []
        namespaces[ns].append((local_name, str(obj)))
    return namespaces
    
    
# Function to group triples by namespace and concatenate values for the same key.
def group_and_concatenate_triples(graph):
    namespaces = {}
    for subject, predicate, obj in graph:
        # Split predicate into namespace and local name
        ns, local_name = predicate.split("#") if "#" in predicate else predicate.rsplit("/", 1)
        value = str(obj)
        # Initialize namespace if not already present
        if ns not in namespaces:
            namespaces[ns] = {}
        # Concatenate values for the same key
        if local_name in namespaces[ns]:
            namespaces[ns][local_name] += f", {value}"
        else:
            namespaces[ns][local_name] = value
    return namespaces


# 6. Choose method for handling multiple values for the same key
print("\nChoose how to handle multiple values for the same key:")
print("1. Separate key-value pairs for each value. Example: key1:value1, key1:value2, key1:value3")
print("2. Concatenate all values for the same key. Example: key1:value1, value2, value3")
choice = input("Enter your choice (1 or 2): ")

if choice == "1":
    namespaces = group_triples_by_namespace(graph)
elif choice == "2":
    namespaces = group_and_concatenate_triples(graph)
else:
    print("Invalid choice. Exiting.")
    exit(1)


# 7. Upload namespaces and key-value pairs as OMERO MapAnnotations
try:
    image = conn.getObject("Image", int(image_id))
    if not image:
        print(f"Image with ID {image_id} not found.")
        exit(1)

    for ns, key_value_pairs in namespaces.items():
        map_ann = omero.model.MapAnnotationI()
        map_ann.setNs(omero.rtypes.rstring(ns))  # Set the full namespace as the OMERO annotation namespace

        # Prepare key-value pairs for this namespace
        if isinstance(key_value_pairs, list):  # For separate key-value pairs
            map_values = [omero.model.NamedValue(key, value) for key, value in key_value_pairs]
        else:  # For concatenated key-value pairs
            map_values = [omero.model.NamedValue(key, value) for key, value in key_value_pairs.items()]

        map_ann.setMapValue(map_values)

        # Save the annotation to the OMERO server
        map_ann = conn.getUpdateService().saveAndReturnObject(map_ann)

        # Link the annotation to the image
        link = omero.model.ImageAnnotationLinkI()
        link.setParent(omero.model.ImageI(image.getId(), False))  # Link to the image
        link.setChild(map_ann)
        conn.getUpdateService().saveObject(link)

    print("Annotations successfully uploaded to OMERO.")
except Exception as e:
    print(f"An error occurred while uploading annotations: {e}")

# Disconnect
conn.close()
print("Disconnected from OMERO.")


