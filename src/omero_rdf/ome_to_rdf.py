from ome_types import OME as Ome
from rdflib import BNode, Graph, Namespace, URIRef, RDF, RDFS, SDO, Literal
from rdflib.namespace import DefinedNamespace

class OME(DefinedNamespace):
    _NS = Namespace("http://www.openmicroscopy.org/Schemas/OME/2016-06#")
    name: URIRef
    Microscope: URIRef
    Detector: URIRef
    Objective: URIRef
    OMEImage: URIRef
    Channel: URIRef

class OBI(DefinedNamespace):
    _NS = Namespace("http://purl.obolibrary.org/obo/")

    ImageDataSet: URIRef
    Image: URIRef
    ImageCreation: URIRef
    Microscope: URIRef
    Device: URIRef
    MolecularEntity: URIRef
    MolecularLabelRole: URIRef
    InformationContentEntity: URIRef

    hasSpecifiedInput: URIRef
    hasSpecifiedOutput: URIRef
    partOf: URIRef
    hasPart: URIRef
    realizes: URIRef

class BioSchemasDrafts(DefinedNamespace):
    _NS = Namespace("http://bioschemas.org/draft_terms/")

    LabProcess: URIRef
    executesLabProtocol: URIRef

def add_tiff_metadata(
    ome: Ome,
) -> Graph:
    """
    Reads OME-TIFF metadata and converts it to OBI + Schema.org metadata

    Params:
        ome: OME metadata derived from the TIFF
    """

    graph = Graph()

    for experiment in ome.experiments:
        # Make a dataset for each experiment
        dataset_entity = BNode()
        graph.add((dataset_entity, RDF.type, OBI.ImageDataSet))
        if experiment.description:
            # There is no name field for experiments in OME
            # so we use the description as the name
            graph.add((dataset_entity, RDFS.label, Literal(experiment.description)))
            graph.add((dataset_entity, SDO.name, Literal(experiment.description)))
            graph.add((dataset_entity, SDO.description, Literal(experiment.description)))

    # The process that created the images
    process = BNode()
    graph.add((process, RDF.type, OBI.ImageCreation))
    graph.add((process, RDF.type, BioSchemasDrafts.LabProcess))

    for instrument in ome.instruments:
        if (_microscope := instrument.microscope) is None:
            # If there is no microscope, we skip this instrument entirely, including its detectors and objectives
            continue

        microscope_entity = BNode()
        graph.add((microscope_entity, RDF.type, OME.Microscope))
        graph.add((microscope_entity, RDF.type, OBI.Microscope))

        # The process used this microscope
        graph.add((process, SDO.instrument, microscope_entity))
        graph.add((process, OBI.hasSpecifiedInput, microscope_entity))

        for _detector in instrument.detectors:
            # TODO: add specific detector properties
            detector_entity = BNode()
            graph.add((detector_entity, RDF.type, OME.Detector))
            graph.add((detector_entity, RDF.type, OBI.Device))
            graph.add((detector_entity, OBI.partOf, microscope_entity))
            graph.add((detector_entity, SDO.partOf, microscope_entity))

        for _objective in instrument.objectives:
            # TODO: add specific objective properties
            objective_entity = BNode()
            graph.add((objective_entity, RDF.type, OME.Objective))
            graph.add((objective_entity, RDF.type, OBI.Device))
            graph.add((objective_entity, OBI.partOf, microscope_entity))
            graph.add((objective_entity, SDO.partOf, microscope_entity))

    for image in ome.images:
        image_entity = BNode()
        graph.add((image_entity, RDF.type, OME.OMEImage))
        graph.add((image_entity, RDF.type, SDO.ImageObject))
        graph.add((image_entity, RDF.type, OBI.Image))

        # The process produced this image
        graph.add((process, SDO.result, image_entity))
        graph.add((process, OBI.hasSpecifiedOutput, image_entity))

        if image.name is not None:
            graph.add((image_entity, SDO.name, Literal(image.name)))
            graph.add((image_entity, RDFS.label, Literal(image.name)))

        for channel in image.pixels.channels:
            stain_entity = BNode()
            graph.add((stain_entity, RDF.type, SDO.BioChemEntity))
            graph.add((stain_entity, RDF.type, OBI.MolecularEntity))
            
            stain_role = BNode()
            graph.add((stain_role, RDF.type, SDO.Role))
            graph.add((stain_role, RDF.type, OBI.MolecularLabelRole))

            # The stain entity plays the role of a molecular label
            graph.add((stain_entity, OBI.realizes, stain_role))

            channel_entity = BNode()
            graph.add((channel_entity, RDF.type, OME.Channel))
            graph.add((channel_entity, RDF.type, SDO.ImageObject))
            # The channel is part of the image 
            graph.add((channel_entity, OBI.partOf, image_entity))
            graph.add((channel_entity, SDO.isPartOf, image_entity))

            # Channel name and description
            if channel.name is not None:
                graph.add((channel_entity, SDO.name, Literal(f"{channel.name} Channel")))
                graph.add((channel_entity, SDO.description, Literal(f"Image channel that captures {channel.name} fluorescence")))

            # The channel measures the stain
            graph.add((channel_entity, OBI.isQualityMeasurementOf, stain_entity))
            graph.add((stain_entity, OBI.hasMeasurementValue, channel_entity))

    return graph
