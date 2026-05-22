/*
Movilidad - Local Development Schema
=====================================
Mirrors the production Movilidad schema (source: schemas.json).
Used for local integration testing of the MovilidadBridge ETL layer.

NOTE: anticipacion and celular_fijo are intentionally NOT NULL with
DEFAULT 0 to match production. The bridge inserts 0 for both because
these fields are cloud-only ML scores unavailable from the SDK.
*/

IF NOT EXISTS (SELECT * FROM sys.databases WHERE name = 'Movilidad')
BEGIN
    CREATE DATABASE Movilidad;
END
GO

USE Movilidad;
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Transporte')
BEGIN
    CREATE TABLE Transporte (
        IdOffload         INT           NULL,
        FechaOffload      DATE          NULL,
        usuario           NVARCHAR(100) NOT NULL,
        viaje             NVARCHAR(100) NOT NULL,
        modo_transporte   NVARCHAR(50)  NOT NULL,
        comienzo          DATETIME      NOT NULL,
        fin               DATETIME      NOT NULL,
        duracion          INT           NOT NULL,
        metadata          TEXT          NULL,
        velocidad_maxima  FLOAT         NOT NULL
    );
END
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Recorridos')
BEGIN
    CREATE TABLE Recorridos (
        IdOffload         INT           NULL,
        FechaOffload      DATE          NULL,
        usuario           NVARCHAR(100) NOT NULL,
        viaje             NVARCHAR(100) NOT NULL,
        distancia_m       FLOAT         NOT NULL,
        polyline          TEXT          NOT NULL,
        puntos_recorrido  TEXT          NULL,
        ubicacion_inicio  TEXT          NULL,
        ubicacion_fin     TEXT          NULL,
        maxima_velocidad  FLOAT         NOT NULL
    );
END
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'PuntajesPrirmariosTr')
BEGIN
    CREATE TABLE PuntajesPrirmariosTr (
        IdOffload    INT           NULL,
        FechaOffload DATE          NULL,
        usuario      NVARCHAR(100) NOT NULL,
        viaje        NVARCHAR(100) NOT NULL,
        legal        FLOAT         NOT NULL,
        suavidad     FLOAT         NOT NULL,
        atencion     FLOAT         NOT NULL,
        promedio     FLOAT         NOT NULL
    );
END
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'PuntajesSecundariosTr')
BEGIN
    CREATE TABLE PuntajesSecundariosTr (
        IdOffload          INT           NULL,
        FechaOffload       DATE          NULL,
        usuario            NVARCHAR(100) NOT NULL,
        viaje              NVARCHAR(100) NOT NULL,
        concentracion      FLOAT         NOT NULL,
        aceleracion_fuerte FLOAT         NOT NULL,
        frenado_fuerte     FLOAT         NOT NULL,
        curvas_fuertes     FLOAT         NOT NULL,
        anticipacion       FLOAT         NOT NULL DEFAULT 0,
        celular_fijo       INT           NOT NULL DEFAULT 0,
        eventos_fuertes    INT           NOT NULL
    );
END
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Eventos')
BEGIN
    CREATE TABLE Eventos (
        IdOffload           INT           NULL,
        FechaOffload        DATE          NULL,
        usuario             NVARCHAR(100) NOT NULL,
        viaje               NVARCHAR(100) NOT NULL,
        aceleracion         TEXT          NOT NULL,
        uso_telefono        TEXT          NOT NULL,
        curvas              TEXT          NOT NULL,
        celular_fijo        TEXT          NOT NULL,
        frenado             TEXT          NOT NULL,
        exceso_de_velocidad TEXT          NOT NULL,
        llamados            TEXT          NOT NULL,
        pantalla            TEXT          NOT NULL
    );
END
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'EventosSignificantes')
BEGIN
    CREATE TABLE EventosSignificantes (
        IdOffload       INT           NULL,
        FechaOffload    DATE          NULL,
        usuario         NVARCHAR(100) NOT NULL,
        viaje           NVARCHAR(100) NOT NULL,
        aceleracion     TEXT          NOT NULL,
        uso_telefono    TEXT          NOT NULL,
        curvas          TEXT          NOT NULL,
        celular_fijo    TEXT          NOT NULL,
        frenado         TEXT          NOT NULL,
        exceso_velocidad TEXT         NOT NULL,  -- nota: sin _de_ (igual que producción)
        llamados        TEXT          NOT NULL,
        pantalla        TEXT          NOT NULL
    );
END
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'PerfilDeUsuario')
BEGIN
    CREATE TABLE PerfilDeUsuario (
        Id            INT           NOT NULL IDENTITY(1,1) PRIMARY KEY,
        Registro      DATETIME      NULL,
        EventoId      INT           NULL,
        usuario       VARCHAR(1000) NULL,
        LeidoFechaHora DATETIME     NULL,
        json          VARCHAR(MAX)  NULL
    );
END
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'ChoqueDeVehiculo')
BEGIN
    CREATE TABLE ChoqueDeVehiculo (
        Id            INT           NOT NULL IDENTITY(1,1) PRIMARY KEY,
        Registro      DATETIME      NULL,
        EventoId      INT           NULL,
        usuario       VARCHAR(1000) NULL,
        LeidoFechaHora DATETIME     NULL,
        json          VARCHAR(MAX)  NULL
    );
END
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'SentianceEventos')
BEGIN
    CREATE TABLE SentianceEventos (
        id           INT           NOT NULL IDENTITY(1,1) PRIMARY KEY,
        sentianceid  VARCHAR(200)  NOT NULL,
        fechahora    DATETIME      NOT NULL,
        json         VARCHAR(MAX)  NOT NULL,
        tipo         VARCHAR(200)  NOT NULL,
        created_at   DATETIME      NULL,
        procesado    BIT           NULL,
        app_version  VARCHAR(50)   NULL
    );
END
GO

PRINT 'Movilidad schema (local dev) initialized successfully.';
GO
